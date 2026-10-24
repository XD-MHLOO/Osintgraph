import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List

import instaloader
from instaloader.exceptions import InvalidArgumentException, ProfileNotExistsException
from tqdm import tqdm
from google.api_core.exceptions import ResourceExhausted, TooManyRequests

from .credential_manager import get_credential_manager
from .get_session import *
from .services.llm_analyzer import LLMAnalyzer
from .services import llm_models
from .neo4j_manager import *
from .utils.data_extractors import (
    extract_comment_data,
    extract_post_data,
    extract_profile_data,
    extract_user_metadata,
)




@dataclass
class Insta_Config:
    limits: Dict[str, int] = field(default_factory=lambda: {
        'followers': 1000,
        'followees': 1000,
        'posts'     : 10,
    })
    # batch_mode_allowed: bool = False
    skip_followers: bool = False
    skip_followees: bool = False
    skip_posts: bool = False
    skip_posts_analysis: bool = False
    skip_account_analysis: bool = False
    max_request: int = 200
    debug_mode: bool = False
    force: List[str] = field(default_factory=list)
    auto_login: bool = True

class InstagramManager:
    def __init__(self, config : Insta_Config = Insta_Config()):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG if self.config.debug_mode else logging.INFO)
        self.L = instaloader.Instaloader(compress_json=False)
        self.L.context.error = lambda *args, **kwargs: None

        self.request_made = 0
        self.credential_manager = get_credential_manager()
        self._neo4j_manager = None  # private attribute for lazy init
        self.llmanalyzer = LLMAnalyzer()
        self.username = ""
        self.key_lock = asyncio.Lock()
        # LLM pre-analysis runs on whichever named provider is configured:
        # Gemini, or OrcaRouter Cyber Inference (API key).
        self.has_llm = llm_models.has_llm_credentials()
        if self.config.auto_login:
            _ = self.neo4j_manager
            self._login()
            self._initialize_neo4j()

    @property
    def neo4j_manager(self):
        """Lazily create Neo4jManager when accessed."""
        if self._neo4j_manager is None:
            self._neo4j_manager = Neo4jManager()
        return self._neo4j_manager
    
    #############################################################################################
    # Public Features 

    ## Collecting target user's profile and connection data
    def discover(self, target_user: str):
        data_types = ['followers', 'followees', 'posts', 'posts_analysis', 'account_analysis']
        self._rate_limit()
        
        self.logger.info("PROFILE -")
        self.logger.info("⧗  Starting to fetch Profile...")
        try:
            profile = instaloader.Profile.from_username(self.L.context, target_user)
        except ProfileNotExistsException:
            self.logger.warning(f"Instagram user: {target_user} does not exist. Make sure the username is correct.")

        try:
            user = extract_profile_data(profile)
        except KeyError:
            self.logger.error("Your Instagram session might be expired. Try the following:\n"
                "                       1. If you log in via Firefox cookie session, re-login to your Instagram account in Firefox and run `osintgraph reset instagram`.\n"
                "                       2. If you log in manually, simply run `osintgraph reset instagram` to re-login."
            )
            return
        existing_user = self.neo4j_manager.execute_write(self.neo4j_manager.get_person_by_username, target_user)
        if existing_user:
            user["account_analysis"] = existing_user.get("account_analysis")

        
        
        self.neo4j_manager.execute_write(self.neo4j_manager.create_user, user)
        
        self.logger.info("✓  Profile fetched")
                
        if user["followees"] == 0 :
            self.neo4j_manager.execute_write(self.neo4j_manager.set_completion_flags, target_user, **{"followees": True})
        if user["followers"] == 0 :
            self.neo4j_manager.execute_write(self.neo4j_manager.set_completion_flags, target_user, **{"followers": True})
        if user["mediacount"] == 0 :
            self.neo4j_manager.execute_write(self.neo4j_manager.set_completion_flags, target_user, **{"posts": True})
            self.neo4j_manager.execute_write(self.neo4j_manager.set_completion_flags, target_user, **{"posts_analysis": True})

        if profile.is_private and not profile.followed_by_viewer:
            self.logger.error(f"Cannot fetch data. {target_user}'s profile is private. Follow the user to access their profile.")
            return
        
        force_all = "all" in self.config.force
        for data_type in data_types:
            print()
            self.logger.info(f"{data_type.upper()} -")
            completions = self.neo4j_manager.execute_read(self.neo4j_manager.get_completion_flags, target_user)
                
            if not getattr(self.config, f"skip_{data_type}"):
                force_this = force_all or data_type in self.config.force
                
                if force_this:
                    
                    self.neo4j_manager.execute_write(self.neo4j_manager.set_completion_flags, target_user, **{data_type: False})

                    if data_type in ['followers', 'followees', 'posts']:
                        self.neo4j_manager.execute_write(self.neo4j_manager.save_resume_hash, profile.userid, {data_type: ""})

                if force_this or not completions.get(data_type, False):

                    if data_type == "posts_analysis":
                        if self.has_llm:
                            self.analyze_post(user["username"])
                        else:
                            self.logger.warning("⤷  Skipped posts_analysis (no LLM provider configured)")

                    elif data_type == "account_analysis":
                        if self.has_llm:
                            self.analyze_account(user["username"])
                        else:
                            self.logger.warning("⤷  Skipped account_analysis (no LLM provider configured)")
                    else:
                        self._fetch_and_map(profile, data_type)

                else:
                    self.logger.info(f"⤷  {data_type.capitalize()} was already completed — skipping")
            else:
                self.logger.info(f"⤷  Skipped {data_type.capitalize()}")

        

        # if self.config.debug_mode:
        #     with open(f"{target_user}_followers.json", "w") as json_file:
        #         json.dump(result['followers'], json_file, indent=4)
        #     self.logger.debug(f"Follower details saved to {target_user}_followers_batch.json.")


        #     with open(f"{target_user}_followees.json", "w") as json_file:
        #         json.dump(result['followees'], json_file, indent=4)
        #     self.logger.debug(f"Followee details saved to {target_user}_followees_batch.json.")
        


    ## Uncovering the network of target user  
    def explore(self, target_user: str, max_people: int = 5):
        result = self.neo4j_manager.execute_read(
            self.neo4j_manager.get_person_by_username, username=target_user
        )
        if not result:
            self.logger.warning(f"User does not exist. Add the user using \"discover {target_user}\", then come and try again.")
            return

        # Fetch famous users once
        famous_users = self._famous(target=target_user)
        if not famous_users:
            self.logger.warning("No famous users found.")
            return

        step = 0
        seen = set()

        for user in famous_users:
            username = user.get('username')
            if not username or username in seen:
                continue

            self.logger.info(f"Discovering: {username}")
            try:
                self.discover(username)
                # self.logger.info(f"Successfully discovered {username}.")
            except Exception as e:
                self.logger.error(f"Error discovering {username}: {e}")
                continue

            seen.add(username)
            step += 1
            print()
            self.logger.info(f"Step {step}/{max_people} complete.")
            time.sleep(random.uniform(5, 10))  # Avoid rate limits

            if step >= max_people:
                break

    #############################################################################################
    # Internal Features
    
    ### Session Handling
    
    ## Account Login (This will first try to login via session file, if not found then relogin is needed )
    def _login(self):
        self.user_agent = self.credential_manager.get("INSTAGRAM_USER_AGENT")
        if self.user_agent:
            self.L.context.user_agent = self.user_agent
        # Try to fetch the username from the environment
        self.username = self.credential_manager.get("INSTAGRAM_USERNAME")

        if not self.username:
            self.logger.warning("⚠  Instagram Login Required.")
            self.choose_login_method()
            return
        try:        
            self.L.load_session_from_file(self.username)  # Try loading the session file
            self.logger.info(f"✓  Logged in as {self.username}.")
        except FileNotFoundError:
            self.logger.warning(f"✗ USER: {self.username} Session file not found")
            self.logger.warning("Instagram Login required.")
            self.choose_login_method()
        except CookieFileNotFoundError: 
            self.logger.warning("Cookie file not found. Please check your Firefox cookies file.")
            self.logger.warning("Instagram Login required.")
            self.choose_login_method()
        except NoLoginInError:
            self.logger.warning("Make sure you have logged in successfully in Firefox")
            self.logger.warning("Instagram Login required.")
            self.choose_login_method()
        except Exception as e:
            self.logger.error(f"Unexpected error occurred: {e}")
            self.logger.warning("Instagram Login required.")
            self.choose_login_method()

        
        
    def choose_login_method(self):
        self.logger.info(
            "[1] Login via Firefox Cookie Session (Recommended – avoids suspicious detection)\n"
            "                       Just make sure you're already logged into Instagram in Firefox – your session will be auto-extracted.\n"
            "                       [2] Manual Login (Enter your username and password manually)"
        )
        self.logger.info("Choose a login method: ")
        choice = input("                       > ")
        try: 
            
            if (choice == "1"):
                self.logger.info("Login via Firefox's Cookie Session")
                self.logger.info("Enter your Instagram username:")
                self.username = input("                       > ")
                import_session(get_cookiefile(), None)
                self.L.load_session_from_file(self.username)  # Try loading the session file
                self.logger.info(f"✓  Logged in as {self.username}.")
            else:
                self.logger.info("Manual Login")
                self.logger.info("Enter your Instagram username:")
                self.username = input("                       > ")
                self.L.interactive_login(self.username)  # Log in interactively
                self.L.save_session_to_file()  # Save session to file for later use
                self.logger.info(f"✓  Logged in as {self.username}.")

            self.credential_manager.set("INSTAGRAM_USERNAME", self.username)

        except FileNotFoundError:
            self.logger.warning(f"✗ USER: {self.username} Session file not found")
            self.logger.warning("Instagram Login required.")
            self.choose_login_method()
        except CookieFileNotFoundError: 
            self.logger.warning("Cookie file not found. Please check your Firefox cookies file.")
            self.logger.warning("Instagram Login required.")
            self.choose_login_method()
        except NoLoginInError:
            self.logger.warning("Make sure you have logged in successfully in Firefox")
            self.logger.warning("Instagram Login required.")
            self.choose_login_method()
        except Exception as e:
            self.logger.error(f"Unexpected error occurred: {e}")
            self.logger.warning("Instagram Login required.")
            self.choose_login_method()

      

    ## Neo4j Initialization (This will check if your database constraints exit, if not will  create constriants for your database )
    def _initialize_neo4j(self):
        
        self.neo4j_manager.execute_write(self.neo4j_manager.create_unique_constraint)
        self.neo4j_manager.execute_write(self.neo4j_manager.create_vector_indexes)

    ### Data Fetching 

    ## Fetch and parse user data via Instaloader
    def _fetch_and_map(self, profile, data_type):
        max_count = self.config.limits[data_type]
        if max_count == 0:
            self.logger.info(f"Skipping {data_type} as max_count is 0.")
            return

        options = {
            'followers': {
                'method' : profile.get_followers,
                'count'  : profile.followers
            },
            'followees': {
                'method' : profile.get_followees,
                'count'  : profile.followees
            },
            'posts'    : {
                'method' : profile.get_posts,
                'count'  : profile.mediacount
            }
            
        }
        counter = 0
        total_items = min(max_count, options[data_type]['count'])
        resume_hash_created = False

        try:

            if data_type in ("followers", "followees"):
                
                method = options[data_type]['method']
                iterator, is_resume = self.maybe_resume_iterator(method, data_type, profile.username)
                if is_resume:
                    self.logger.info(f"♻  Resuming unfinished {data_type.capitalize()} fetch...")
                else:
                    self.logger.info(f"⧗  Starting to fetch {data_type.capitalize()}...")

                result = {
                    data_type: {
                        "data": [],
                        "batch_mode": is_resume
                    }
                }

                for person in tqdm(iterator, desc=f"Fetching {data_type}", unit="people", total=total_items, ncols=70):
                    
                    if counter >= max_count:
                        result[data_type]["batch_mode"] = True
                        resume_hash = {
                            data_type: json.dumps(instaloader.get_json_structure(iterator.freeze()))
                        }
                        self.neo4j_manager.execute_write(self.neo4j_manager.save_resume_hash, profile.userid, resume_hash)
                        resume_hash_created =True
                        break
                    
                    
                    person_data = extract_user_metadata(person)
                    result[data_type]["data"].append(person_data)
                    self.request_made += 1
                    counter +=1

                    if self.request_made % self.config.max_request == 0:
                        time.sleep(random.uniform(8, 10))
                    
                    

                if result[data_type]["data"]:
                    self.neo4j_manager.execute_write(self.neo4j_manager.create_users, result[data_type]["data"])
                    self.logger.debug(f"Successfully added {data_type}.")
                    self.neo4j_manager.execute_write(self.neo4j_manager.manage_follow_relationships, profile.userid, result)
                    
                if resume_hash_created:
                    self.logger.info(f"✓  {data_type.capitalize()} fetched (partially)")
                    self.logger.info(f"✎  Saved resume point for {data_type.capitalize()}")
                else:
                    self.neo4j_manager.execute_write(self.neo4j_manager.set_completion_flags, profile.username, **{data_type: True} )
                    self.neo4j_manager.execute_write(self.neo4j_manager.save_resume_hash, profile.userid, {data_type: ""})
                    self.logger.info(f"✓  {data_type.capitalize()} fetched")


            elif data_type == "posts":
                method = options[data_type]['method']
                iterator, is_resume = self.maybe_resume_iterator(method, data_type, profile.username)
                
                if is_resume:
                    self.logger.info(f"♻  Resuming unfinished {data_type.capitalize()} fetch...")
                else:
                    self.logger.info(f"⧗  Starting to fetch {data_type.capitalize()}...")

                result = {
                    data_type: {
                        "data": None,
                        "batch_mode": is_resume
                    }
                }
                for post in tqdm(iterator, desc=f"Fetching {data_type}", unit="post", total=total_items, ncols=70):
                    
                    if counter >= max_count:
                        result[data_type]["batch_mode"] = True
                        resume_hash = {
                            data_type: json.dumps(instaloader.get_json_structure(iterator.freeze()))
                        }
                        self.neo4j_manager.execute_write(self.neo4j_manager.save_resume_hash, profile.userid, resume_hash)
                        resume_hash_created =True
                        break
                    
                    # if getattr(post, 'typename', None) == "GraphSidecar":
                    #     post.sidecars = []
                    #     for sidecar in post.get_sidecar_nodes(start=0, end=-1):
                    #         post.sidecars.append({"display_url":sidecar.display_url,"is_video":sidecar.is_video, "video_url":sidecar.video_url})
                    #     post.sidecars = json.dumps(post.sidecars)
                    
                    post.comments_details = {
                        'comments_list'   : [],
                        'commentors_list' : [],
                        'likers_list'      : [],
                    }
                    post.likers_list = []

                    for comment in post.get_comments():
                        post.comments_details['comments_list'].append({'reply_id': None , **extract_comment_data(comment)})
                        post.comments_details['commentors_list'].append(extract_user_metadata(comment.owner))
                        
                        for liker in comment.likes:
                            post.comments_details['likers_list'].append({'liked_comment_id': int(comment.id), **extract_user_metadata(liker)})
                        
                        for ans in comment.answers:
                            post.comments_details['comments_list'].append({'reply_id': int(comment.id), **extract_comment_data(ans)})
                            post.comments_details['commentors_list'].append(extract_user_metadata(ans.owner))
                    
                    for liker in post.get_likes():
                        post.likers_list.append({'liked_post_id': int(post.mediaid), **extract_user_metadata(liker)})
                        
                    
                    result[data_type]["data"] = extract_post_data(post)

                    self.neo4j_manager.execute_write(self.neo4j_manager.manage_post_relationships, result[data_type]["data"])
                    self.neo4j_manager.execute_write(self.neo4j_manager.set_completion_flags, profile.username, **{"posts_analysis": False})
                    self.neo4j_manager.execute_write(self.neo4j_manager.set_completion_flags, profile.username, **{"account_analysis": False})

                    self.logger.debug(f"Successfully added {data_type}.")

                    self.request_made += 1
                    counter +=1
                    if self.request_made % self.config.max_request == 0:
                        time.sleep(random.uniform(10, 15))
                    

                    
                if resume_hash_created:
                    self.logger.info(f"✓  {data_type.capitalize()} fetched (partially)")
                    self.logger.info(f"✎  Saved resume point for {data_type.capitalize()}")
                else:
                    self.neo4j_manager.execute_write(self.neo4j_manager.save_resume_hash, profile.userid, {data_type: ""})
                    self.neo4j_manager.execute_write(self.neo4j_manager.set_completion_flags, profile.username, **{data_type: True} )
                    self.logger.info(f"✓  {data_type.capitalize()} fetched")
                


        except KeyboardInterrupt:
            # instaloader.save_structure_to_file(iterator.freeze(), "resume_info.json")
            pass

    def analyze_post(self, username: str):
        self.logger.info(f"⧗  Starting to analyze Posts with LLM...")
        total_items = self.neo4j_manager.execute_read(self.neo4j_manager.count_posts_unanalyzed_by_username, username)
        iterator = self.neo4j_manager.get_posts_unanalyzed_by_username(username)
        try:
            for post in tqdm(iterator, desc=f"Analyzing Post", unit="post", total=total_items, ncols=70):
                self.llmanalyzer.process_post(self, post)
            
            self.neo4j_manager.execute_write(self.neo4j_manager.set_completion_flags, username, **{"posts_analysis": True})
            self.logger.info(f"✓  Posts Analysis Completed")
            return True
        
        except (ResourceExhausted, TooManyRequests) as e:
            self.logger.warning(f"⚠  Rate limit hit. Post analysis Incomplete.")
            return False
        except RuntimeError as e:
            self.logger.error(f"⚠  Runtime error. Post analysis Incomplete.")
            return False
        except Exception as e:
            if "API_KEY_INVALID" in str(e):
                    if llm_models.get_llm_provider() == llm_models.orcarouter.PROVIDER_ID:
                        self.logger.error(f"⚠  OrcaRouter API key is invalid. Please run `osintgraph setup orcarouter` to update it.")
                    else:
                        self.logger.error(f"⚠  Gemini API key is invalid. Please run `osintgraph reset gemini` to update it.")
                    return False
            self.logger.error(f"⚠  Post analysis Failed. Unknown error  {e}")
            return False


    def analyze_account(self, username: str):
        completions = self.neo4j_manager.execute_read(self.neo4j_manager.get_completion_flags, username)
        self.logger.info(f"⧗  Starting to analyze Account with LLM...")
        
        if not completions.get("posts_analysis", False):
            self.logger.warning(f"⚠  Account analysis requires complete post analysis — running now.")
            post_success = self.analyze_post(username)
            if not post_success:
                self.logger.error("⚠ Post analysis failed — skipping account analysis.")
            return 
        
        
        try:
            self.llmanalyzer.process_account(self, username)
            self.neo4j_manager.execute_write(self.neo4j_manager.set_completion_flags, username, **{"account_analysis": True})
            self.logger.info(f"✓  Account Analysis Completed")
        except (ResourceExhausted, TooManyRequests) as e:
            self.logger.warning(f"⚠  Rate limit hit. Post analysis Incomplete.")
        except RuntimeError as e:
            self.logger.error(f"⚠  Runtime error. Post analysis Incomplete.")
        except Exception as e:
            self.logger.error(f"⚠  Post analysis Failed. Unknown error  {e}")

    ## Finds the most popular user based on a given criterion (e.g., followers, date).
    def _famous(self, target: str, limit: int = 100):
        """
        Find a popular user (by followers count) from the followees of `target`
        who still requires further discovery (incomplete profile or graph data).
        """
        self.logger.info("Finding top followees for discovery...")

        # Try users with incomplete profile
        result = self.neo4j_manager.execute_read(
            self.neo4j_manager.find_incomplete_followees_by_popularity, target
        )

        # Fallback: users with incomplete followers/followees/posts
        if not result:
            self.logger.debug("No incomplete-profile users found, checking graph-incomplete ones.")
            result = self.neo4j_manager.execute_read(
                self.neo4j_manager.find_incomplete_targets, target
            )

        if not result:
            # self.logger.debug("No famous user found.")
            return []

        # Return at most `limit` results
        return [record.data() for record in result][:limit]

    
    ### Resume Hash Logic 
    def maybe_resume_iterator(self, method, data_type: str, username: str):
        iterator = method()
        is_resume = False
        resume_hash = self.neo4j_manager.execute_read(
            self.neo4j_manager.get_resume_hashes,
            username,
            [data_type]
        )

        if resume_hash.get(data_type):
            is_resume = True
            try:
                iterator.thaw(instaloader.load_structure(self.L.context, json.loads(resume_hash[data_type])))
            except InvalidArgumentException as e:
                iterator = method()  # Recreate iterator from scratch
                self.logger.warning(f"⚠  {e} for {username}. Restarting from scratch.")


        return iterator, is_resume


    ### Temporary Configuration 

    ## Temporary config 
    # @contextmanager
    # def _temporary_config(self, new_config):

    #     original_config = self.config
    #     self.config = new_config

    #     try:
    #         #Yield control to the "with" block
    #         yield
    #     finally:

    #         self.config = original_config

    ### Rate limiting

    ## Rate limit
    def _rate_limit(self):
        if self.request_made > 2000:
            self.logger.info("Count exceeded 2000. Pausing for 10 minutes before continuing session.")
                
            # Save the session before sleeping
            self.L.save_session_to_file()
            # self.logger.info("Session saved. Sleeping for 10 minutes.")
            
            time.sleep(600)  # Sleep for 10 minutes

            # After sleep, reload the session to continue
            self.L.load_session_from_file(self.username)
            self.logger.info("Session reloaded after 10 minutes sleep.")





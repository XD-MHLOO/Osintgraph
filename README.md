# Osintgraph (Open Source Intelligence Graph)

![osintgraph_banner](https://github.com/user-attachments/assets/04a46de3-8f0e-40fa-83f6-2a9ff811a667)

**Osintgraph** is a tool for deep social analysis and OSINT investigations focused on Instagram targets.
It uses Neo4j to map a target’s network — revealing connections, interests, and affiliations — and an interactive AI Agent to speed up investigations and simplify analysis.

## ⚡ What OSINTGraph Does
**OSINTGraph CLI** gathers all public Instagram data from a target and maps their social connections, including **profiles**, **followers**, **followees**, **posts**, **comments**, and **likes**. It helps you thoroughly examine your target by gathering all relevant data and analyzing it for investigations.

[See how it works ↗](#-how-osintgraph-works)

### Data collection via CLI:
| ![osintgrah_cli](https://github.com/user-attachments/assets/131fca5d-a0ac-4193-bf7c-af52bafc75b1) |
|-----------------|
| *Overview of CLI Interface for data collection* |

### Explore and analyze your target's data via two ways:

### 1. **Osintgraph AI Agent**
Use natural language to query about your target.
The AI Agent supports data retrieval, keyword and semantic searches, relationship queries, and template-driven analyses — helping you get focused answers without manually digging through data.
| [![asciicast](https://asciinema.org/a/732693.svg)](https://asciinema.org/a/732693) |
|-----------------|
| *Overview of interacting with the agent performing data retrieval, keyword and semantic searches, and template-based analyses.* |

### 2. **Neo4j Visualization**
Visualize your target’s social network, trace interactions, and query relationships directly.  

[![video](https://github.com/user-attachments/assets/71a6c81c-655e-4831-83e8-585e9d270b5a)](https://github.com/user-attachments/assets/71a6c81c-655e-4831-83e8-585e9d270b5a)

| *Example of tracing a target user’s close connection through their most commented post, then investigating mutual followers and all interactions between them.* |
|-----------------|




## 📚 Table of Contents

* [✨ About OSINTGraph](#osintgraph-open-source-intelligence-graph)  
* [⚡ What OSINTGraph Does](#-what-osintgraph-does)  
* [🚀 Getting Started](#-getting-started)  
  * [1. Install OSINTGraph](#1-install-osintgraph)  
  * [2. Setup Configuration](#2-setup-configuration)  
  * [3. Start Collecting Instagram Data](#3-start-collecting-instagram-data)  
  * [4. Analyze & Investigate](#4-analyze--investigate)  
  * [5. Visualize in Neo4j](#5-visualize-in-neo4j)
* [⚡ How OSINTGraph Works](#-how-osintgraph-works)  
  * [Phase 1: Reconnaissance](#phase-1-reconnaissance)  
  * [Phase 2: Analysis & Investigation](#phase-2-analysis--investigation)  
* [⚙ Commands Reference](#-commands-reference)  
  * [`setup`](#-setup-option)  
  * [`reset`](#-reset-option)  
  * [`discover`](#-discover-username)  
  * [`explore`](#-explore-username)  
  * [`agent`](#-agent)  
* [🧩 Data Model (Neo4j Schema)](#-data-model-neo4j-schema)  
  * [👤 Person Node](#-person---represents-an-instagram-account)
  * [📷 Post Node](#-post---represents-an-instagram-post)
  * [💬 Comment Node](#-comment---represents-a-comment-on-a-post) 
  * [🕸️ Relationships](#-relationships)
* [🕵️ OSINTGraph AI Agent – Getting Started Guide](#-osintgraph-ai-agent--getting-started-guide)  
  * [1. 🔧 Data Retrieval](#1--data-retrieval)  
    * [Approach 1: Basic Data Retrieval](#approach-1-basic-data-retrieval)  
    * [Approach 2: Relationship Traversal](#approach-2-relationship-traversal)  
    * [Approach 3: Content Search](#approach-3-content-search)  
    * [Combining Approaches](#combining-approaches)  
    * [Best Practices – How to Ask Questions for Best Results](#-best-practices--how-to-ask-questions-for-best-results)  
  * [2. 📝 Template-Based Analysis](#2--template-based-analysis)  
    * [⚡How Templates Work](#-how-templates-work)  
    * [🛠 How to Create Custom Templates](#-how-to-create-your-own-custom-template)  
* [🚫 How to Avoid Account Suspension](#-how-to-avoid-account-suspension)  
* [📦 Dependencies](#-dependencies)  

## 🚀 Getting Started
### 1. Install OSINTGraph
```bash
pipx install osintgraph
```
or
```bash
pip install osintgraph
```
> [!NOTE]
> When using pip, it’s recommended to install inside a Python virtual environment to avoid dependency conflicts.

### 2. Setup Configuration 
Before running `osintgraph setup`, make sure you have the following ready:

- **Instagram Account:** Preferably not your main account

- **Neo4j Database:** For storing and visualizing data.
  
  (Sign up at [Neo4j](https://neo4j.com) → Create an instance for free → Download admin credentials) — you’ll need these for connection.

- **Gemini API Key:** Enables data pre-analyses and the AI agent.
  
  (Sign up at [Google AI Studio](https://aistudio.google.com) → Create or select a Google Cloud project → Get API Key for free)

- **User Agent (Optional):** Helps reduce Instagram detection risk.
  (Open your Firefox browser where you log in to Instagram, search “my user agent” on Google, and copy it)

Then run 
```bash
osintgraph setup
```

### 3. Start collecting Instagram data
Start gathering data on your target:
```bash
osintgraph discover TARGET_INSTAGRAM_USERNAME --limit follower=100 followee=100 post=2 
```
### 4. Analyze & Investigate
Launch the AI Agent to explore and analyze collected data:
```bash
osintgraph agent
```
Once the agent starts, try asking it:
```Show the target user’s profile info```

### 5. Visualize in Neo4j
Explore your target’s network graph interactively.
- Go to the [Neo4j Console](https://console-preview.neo4j.io/tools/explore).
- Click the **Explore tab**, then **Connect**.
- In the search bar, type "Show me a graph".
- You should now see the person you just collected, along with their relationships.


## ⚡ How OSINTGraph Works

**OSINTGraph run in two main phases: [Reconnaissance](#phase-1-reconnaissance) and [Analysis & Investigation](#phase-2-analysis--investigation).**



```bash
   ⚡PHASE 1: RECONNAISSANCE                                           ⚡PHASE 2: ANALYSIS & INVESTIGATION
   ──────────────────────────                                           ───────────────────────────────────
   [ Data Collection ] (osintgraph discover <target>)                    [ Investigation ] 
     ├─ Profile Metadata                                                   ├─ [AI Agent] (osintgraph agent)
     ├─ Followers                                                          │    • Retrieve Data    
     ├─ Followees                                                          │    • Keyword Search
     └─ Posts (with Comments)                                              │    • Semantic Search
           ↓                                                               │    • Graph Relationship Search
   Posts Pre-Analysis                                                      │    • Run Template Analyses
     ├─ Uses:                                                              └─ [Neo4j Visualization]
     │    • Post Metadata
     │    • Comments
     │    • Image Pre-Analyses
     │         ├─ Uses:
     │         │    • Post media (thumbnails & images)
     │         └─ Generates:
     │              • Structured Image Analysis Report
     └─ Generates:
          • Structured Post Analysis Report
            ↓
    Account Pre-Analysis
      ├─ Uses:
      │    • All Post Analyses
      │    • Profile Metadata
      └─ Generates:
           • Structured Account Analysis Report

```

### Phase 1: Reconnaissance
In this phase, you **collect all public Instagram data** for a target and their network.
You’re building the raw intelligence database that you’ll investigate later.

**What you do:**

Run one of these commands to collect all public Instagram data for a target and their network:

- `osintgraph discover <target>` — Collect and (optionally) pre-analyze the target account’s data.

- `osintgraph explore <target>` — Recursively run `discover` on each followee of the target, prioritizing followees with the largest follower base in the Neo4j database.

**What OSINTGraph does in the background:**
1. Scrapes the target’s profile, followers, followees, posts, and comments.
2. If Gemini API is enabled, pre-analyzes:
   - Image Analysis: Each post’s media is examined for visual clues and details.
   - Post Analysis: Combines image findings, post metadata, and comments into a structured OSINT report.
   - Account Analysis: Summarizes patterns and behaviors across all posts for the account.
   > Pre-analysis quickly examines posts and account data to give you early insights. It’s also useful for template-based investigations, because templates can use the pre-analyzed data immediately for deeper analysis.
3. Maps all relationships (likes, follows, replies, etc.) into Neo4j. [See how Instagram data is stored in Neo4j ↗](#-data-model-neo4j-schema)


### Phase 2: Analysis & Investigation

In this phase, you **search**, **analyze**, and **visualize** the intelligence gathered in Phase 1.
Now you’re making sense of the network, activities, and patterns.

**What you do:**
- **Query** data using natural language, keyword/semantic search, and graph-relationship queries.
- **Run** analyses using predefined or custom templates.
- **Explore and Visualize** social networks interactively.


**You have two main ways to do this:**

#### 1. AI Agent  `osintgraph agent`

- Ask questions for data retrieval, keyword and semantic searches, graph-relationship based queries, and analyses using predefined or custom templates.
[Learn more about Agent ↗](#-osintgraph-ai-agent--getting-started-guide)

#### 2. Neo4j Visualization ([Neo4j Console Browser](https://console-preview.neo4j.io/tools/explore))

- Explore visualize the social network map interactively.
- See how people, posts, and interactions are connected.

## ⚙ Commands Reference
Below is a breakdown of each command, what it does, and when to use it.

### 🔧 `setup [option]`

<details>
<summary>See Usage & options</summary>
   
**Purpose:**

Configures services and credentials so OSINTGraph can access Instagram, Neo4j, Gemini.

**Options:**

- `all` (default) — configure everything.

- `instagram` — configure Instagram scraping credentials (cookies/session).

- `neo4j` — set up your Neo4j database connection.

- `gemini` — set your Gemini API key for AI analysis.

- `user-agent` — customize the User-Agent string for scraping.

**When to use:**
Run this the first time you install OSINTGraph or to set credentials.


Examples:

```bash
osintgraph setup
osintgraph setup instagram
```

</details>

### 🔧 `reset [option]`

<details>
<summary>See Usage & options</summary>
   
**Purpose:**
Clears stored credentials for the chosen option and immediately re-runs setup for that option.

**Options:**

- `all` (default) — reset everything and reconfigure.

- `instagram` — reset Instagram credentials.

- `neo4j` — reset Neo4j database connection settings.

- `gemini` — reset your Gemini API key.

- `user-agent` — reset the User-Agent string for scraping.
  
**When to use:**
Use this when you need to change or update your credentials (e.g., expired Instagram session, new API key, changed Neo4j password).

**Examples:**

```bash
osintgraph reset
osintgraph reset instagram
```

</details>


### 🔍 `discover <username>`

<details>
<summary>See Usage & options</summary>
   
**Purpose:**
Collects all public data for a single Instagram account.

**What it does:**

- Scrapes followers, followees, and posts (with comments).

- Runs **AI-powered post analysis** (`post_analysis`) ). (if Gemini is configured)

- Runs **AI-powered account analysis** (`account_analysis`) after all posts are analyzed. (if Gemini is configured)

- Saves everything in Neo4j.


> **Resumable runs**  
> - If `discover` cannot finish scraping or analysis in one run (for example, a target has thousands of followers or many posts), the progress is saved automatically.  
> - Running the same command again with the same target will continue from where it left off until all data and analysis are complete.  
> - Finished sections are skipped on later runs, so no duplicate work is done.  
> - Use `--force` if you want to re-fetch or re-analyze any part (e.g., `--force follower`, `--force account-analysis`).
>
> **Limitation**
> - When scraping followers and followees, only username and basic profile info are collected. To get full profiles, posts, and comments, you need to run `discover` on each account separately.
> - When scraping posts, likes and comments are collected, but only a partial amount may be available due to Instagram’s limitations.


**Options:**

- `--skip [parts]` — skip certain steps.

   *(Options: all, follower, followee, post, post-analysis, account-analysis)*  
   Example: `--skip post-analysis` will skip analyzing posts with AI.
- `--limit TYPE=NUMBER` — limit how many items to fetch per type (default: follower=1000, followee=1000, post=10).

   *(Options: follower, followee, post)*  
   Example: `--limit post=5` — fetches only 5 posts.
- `--rate-limit NUMBER` —  pause for 8–10 minutes after every N request to avoid detection.  
   Example: `--rate-limit 500` will wait 8~10 minutes after every 500 Instagram requests.
- `--force [parts]` — re-fetch or re-analyze even if already done.   

  *(Options: all, follower, followee, post, post-analysis, account-analysis)*  
   Example: `--force account-analysis` — **resets the progress** and reruns the AI analysis on the account data

**When to use:**
First step of any investigation — gets all data for your primary target.

Example:

```bash
osintgraph discover "target_user"
osintgraph discover "target_user" --skip post-analysis account-analysis --limit follower=200 post=15 --force follower followee
```

</details>


### 🌐 `explore <username>`

<details>
<summary>See Usage & options</summary>

**Purpose:**

Recursive discovery — goes beyond your target to their network.

**What it does:**

- Runs `discover` on each followee of the target, prioritizing those with the largest follower counts in your Neo4j database.

> Focuses on followees because they often reveal the target’s real interests, communities, and affiliations—such as local groups, news sources, favorite influencers, or close friends. Within these, accounts with larger follower bases in your Neo4j DB are explored first, increasing the chances of uncovering valuable insights.

- Stops after a set number of accounts.

**Options:**

- `--max NUMBER` — how many accounts to discover in total.
   Example: `--max 10` — the agent will `discover` up to 10 followees of the target, then stop.
  
*(The following options work the same way as in `discover`)*
- `--skip [parts]` — skip certain steps (e.g., post-analysis).

   *(Options: all, follower, followee, post, post-analysis, account-analysis)*
- `--limit TYPE=NUMBER` — limit how many items to fetch per type (default: follower=1000, followee=1000, post=10).

   *(Options: follower, followee, post)*
- `--rate-limit NUMBER` —  pause for 8–10 minutes after every N request to avoid detection.

- `--force [parts]` — re-fetch or re-analyze even if already done.

  *(Options: all, follower, followee, post, post-analysis, account-analysis)*


**When to use:**
To expand your investigation into the wider social network.

Example:

```bash
osintgraph explore "target_user"
osintgraph explore "target_user" --max 10 --limit follower=1000 followee=500
```

</details>


### 🤖 `agent`

<details>
<summary>See Usage & options</summary>

**Purpose:**

Launches the OSINTGraph AI Agent for natural language investigations.

**What it can do:**

- Keyword search across your Neo4j database.

- Semantic search using AI embeddings.

- Auto-generate and run Cypher queries.

- Execute prebuilt or custom YAML investigation templates.

**Key options:**

- `--debug` — store detailed debug output for template.

**When to use:**

After you’ve collected data use the agent to ask questions, run analysis, or execute templates.

Example:

```bash
osintgraph agent --debug
```

</details>


## 🧩 Data Model (Neo4j Schema)
After scraping, OSINTGraph stores Instagram data in Neo4j as interconnected nodes and relationships.
<img width="710" height="447.8" alt="OsintgraphNeo4j" src="https://github.com/user-attachments/assets/dc34d94b-fa2b-43c4-8435-a898c8a4dcb1" />

*OSINTGraph Data Model (All Entities & Relationships)*

### 👤 Person - Represents an Instagram account.

<details>
<summary>See all properties</summary>
   
| Property                          | Type    | Description                                          |
| --------------------------------- | ------- | ---------------------------------------------------- |
| **id**                            | INTEGER | Unique identifier for the person node.               |
| **username**                      | STRING  | Instagram username.                                  |
| **fullname**                      | STRING  | Full display name from profile.                      |
| **bio**                           | STRING  | Profile biography text.                              |
| **followers**                     | INTEGER | Number of followers.                                 |
| **followees**                     | INTEGER | Number of accounts followed.                         |
| **mediacount**                    | INTEGER | Number of posts uploaded.                            |
| **external\_url**                 | STRING  | External link in profile bio.                        |
| **business\_category\_name**      | STRING  | Business category if a business account.             |
| **is\_verified**                  | BOOLEAN | True if the account has a verification badge.        |
| **is\_business\_account**         | BOOLEAN | True if the account is marked as a business account. |
| **has\_highlight\_reels**         | BOOLEAN | True if the user has highlight stories.              |
| **has\_public\_story**            | BOOLEAN | True if the account has public stories.              |
| **is\_private**                   | BOOLEAN | True if the account is private.                      |
| **profile\_pic\_url**             | STRING  | Profile picture URL.                                 |
| **profile\_pic\_url\_no\_iphone** | STRING  | Alternate profile picture URL.                       |
| **biography\_hashtags**           | LIST    | Hashtags used in the bio.                            |
| **biography\_mentions**           | LIST    | Usernames mentioned in the bio.                      |

#### Analysis Fields
| Property              | Type   | Description                           |
| --------------------- | ------ | ------------------------------------- |
| **account\_analysis** | STRING | AI-generated analysis of the account. (stringified JSON)|

<details>
  <summary>Show account_analysis structure</summary>
  <pre><code class="json">
  {
  "account_summary": {
    "who_runs_this_account": {
      "summary": "",
      "confidence": ""
    },
    "what_type_of_account": {
      "label": "",
      "reasoning": "",
      "confidence": ""
    },
    "why_this_account_exists": {
      "main_purpose": "",
      "supporting_signals": []
    },
    "who_is_the_target_audience": {
      "summary": "",
      "reasoning": ""
    },
    "what_it_posts_about": {
      "topic_distribution": [
        {
          "topic": "",
          "percentage": ""
        }
      ]
    },
    "how_often_it_posts": {
      "avg_posts_per_month": "",
      "most_active_days": [],
      "seasonal_patterns": ""
    },
    "who_comments_on_it": {
      "audience_profile": {
        "likely_age_range": "",
        "languages_used": [],
        "comment_style": "",
        "emotional_tone": ""
      },
      "relationship_to_owner": ""
    },
    "how_comments_look": {
      "comment_quality": "",
      "reply_behavior": "",
      "engagement_style": "",
      "detected_bots_or_fake_activity": false
    },
    "notable_flags_or_anomalies": {
      "inconsistencies": [],
      "suspicious_behavior": [],
      "possible_account_switch_history": false
    },
    "language_and_text_patterns": {
      "caption_language": [],
      "common_caption_themes": [],
      "hashtags_usage": "",
      "emoji_usage": "",
      "comment_language_distribution": [],
      "comment_length": ""
    },
    "summary_notes": ""
  }
}
  </code></pre>
</details>


#### Semantic Search Fields
| Property                      | Type | Description                                               |
| ----------------------------- | ---- | --------------------------------------------------------- |
| **username\_vector**          | LIST | Vector embedding of username for semantic search.         |
| **bio\_vector**               | LIST | Vector embedding of biography for semantic search.        |
| **fullname\_vector**          | LIST | Vector embedding of full name for semantic search.        |
| **account\_analysis\_vector** | LIST | Vector embedding of account analysis for semantic search. |

#### Internal Fields
| Property                          | Type    | Description                                    |
| --------------------------------- | ------- | ---------------------------------------------- |
| **\_profile\_complete**           | BOOLEAN | Internal flag: profile scrape completed.       |
| **\_followers\_complete**         | BOOLEAN | Internal flag: follower list scrape completed. |
| **\_followees\_complete**         | BOOLEAN | Internal flag: followee list scrape completed. |
| **\_posts\_complete**             | BOOLEAN | Internal flag: posts scrape completed.         |
| **\_posts\_analysis\_complete**   | BOOLEAN | Internal flag: post analysis completed.        |
| **\_account\_analysis\_complete** | BOOLEAN | Internal flag: account analysis completed.     |
| **\_followers\_resume\_hash**     | STRING  | Internal resume state for follower scraping.   |
| **\_followees\_resume\_hash**     | STRING  | Internal resume state for followee scraping.   |
| **\_posts\_resume\_hash**         | STRING  | Internal resume state for posts scraping.      |

</details>


### 📷 Post - Represents an Instagram post.

<details>
<summary>See all properties</summary>

| Property                   | Type       | Description                                      |
| -------------------------- | ---------- | ------------------------------------------------ |
| **id**                     | INTEGER    | Unique identifier for the post node.             |
| **shortcode**              | STRING     | Instagram post shortcode (URL-friendly ID).      |
| **caption**                | STRING     | Post caption text.                               |
| **pcaption**               | STRING     | Preprocessed caption text (cleaned).             |
| **title**                  | STRING     | Post title (if available).                       |
| **likes**                  | INTEGER    | Number of likes on the post.                     |
| **comments**               | INTEGER    | Number of comments on the post.                  |
| **is\_video**              | BOOLEAN    | True if the post is a video.                     |
| **video\_duration**        | INTEGER    | Video length in seconds.                         |
| **video\_view\_count**     | INTEGER    | Number of video views.                           |
| **is\_pinned**             | BOOLEAN    | True if the post is pinned on profile.           |
| **is\_sponsored**          | BOOLEAN    | True if the post is marked as sponsored content. |
| **typename**               | STRING     | Instagram media type name.                       |
| **mediacount**             | INTEGER    | Number of media items (for carousel posts).      |
| **accessibility\_caption** | STRING     | Alt-text or accessibility caption.               |
| **tagged\_users**          | LIST       | Usernames tagged in the post.                    |
| **caption\_hashtags**      | LIST       | Hashtags used in the post caption.               |
| **caption\_mentions**      | LIST       | Mentions in the post caption.                    |
| **date\_utc**              | DATE\_TIME | UTC timestamp of post creation.                  |
| **date\_local**            | DATE\_TIME | Local timestamp of post creation.                |

#### Analysis Fields
| Property            | Type   | Description                               |
| ------------------- | ------ | ----------------------------------------- |
| **post\_analysis**  | STRING | AI-generated analysis of the post. (stringified JSON)|
| **image\_analysis** | STRING | AI-generated image analysis for the post. (stringified JSON array)|
<details>
  <summary>Show post_analysis structure</summary>
  <pre><code class="json">
    {
  "post_metadata_summary": {
    "post_type": "",
    "post_tone": "",
    "post_intent": "",
    "poster_role_or_affiliation": "",
    "target_audience": "",
    "posting_motivation": "",
    "date_context": "",
    "sponsored_or_promotional": false
  },
  "visual_analysis_summary": {
    "key_findings": "",
    "notable_objects_or_symbols": "",
    "people_or_groups_shown": "",
    "locations_or_geo_clues": "",
    "emotion_or_energy_level": "",
    "forensic_red_flags": []
  },
  "comment_section_analysis": {
    "overall_sentiment": "",
    "common_comment_behaviors": "",
    "dominant_tones_or_emotions": "",
    "top_words_or_emojis": [],
    "interaction_patterns": "",
    "bot_or_coordinated_activity": false,
    "cultural_or_linguistic_signals": ""
  },
  "behavioral_and_social_insight": {
    "likely_poster_motivation": "",
    "social_group_affiliations": "",
    "influence_or_recruitment_signs": "",
    "propaganda_or_polarization_signals": "",
    "deception_or_misinfo_signs": ""
  },
  "osint_value": {
    "intelligence_usefulness": "",
    "recommended_followup": "",
    "confidence_level": "",
    "summary_takeaways": ""
  }
}
  </code></pre>
</details>
<details>
  <summary>Show image_analysis structure</summary>
  <pre><code class="json">
{
  "image_type": "",
  "image_tone": "",
  "image_scenario": "",
  "image_intent": "",
  "people_count_visible": "",
  "people_visibility_level": "",
  "people_gender": "",
  "people_age_range": "",
  "people_ethnicity": "",
  "people_clothing": "",
  "people_accessories": "",
  "people_hair_description": "",
  "people_facial_hair": "",
  "people_face_features": "",
  "people_body_type": "",
  "people_skin_tone": "",
  "people_posture": "",
  "people_actions": "",
  "people_dominant_hand": "",
  "people_walking_style": "",
  "people_emotions": "",
  "people_interaction": "",
  "people_possible_role": "",
  "people_items_carried": "",
  "people_visible_tech": "",
  "people_tattoos_piercings": "",
  "people_symbols_or_badges": "",
  "people_identity_clues": "",
  "people_eye_color": "",
  "people_glasses_or_contacts": "",
  "people_mouth_expression": "",
  "people_visible_injuries": "",
  "people_makeup_or_face_paint": "",
  "people_body_language": "",
  "people_proximity": "",
  "people_group_behavior": "",
  "people_footwear": "",
  "people_carry_method": "",
  "people_visible_tattoos": "",
  "people_eye_contact": "",
  "people_accessory_details": "",
  "people_disabilities_or_devices": "",
  "people_behavior_notes": "",
  "text_present": false,
  "text_transcribed": "",
  "text_language": "",
  "text_font_style": "",
  "text_meaning": "",
  "clothing_style": "",
  "clothing_colors": "",
  "clothing_symbols_or_logos": "",
  "facial_expressions": "",
  "group_mood": "",
  "scene_location_type": "",
  "scene_background": "",
  "scene_time_weather": "",
  "notable_objects": "",
  "tech_or_tools": "",
  "vehicles_or_props": "",
  "visible_text_on_objects": "",
  "uniforms_or_insignia": "",
  "environment_signs": "",
  "editing_or_staging_signs": "",
  "license_plate_number": "",
  "license_plate_region": "",
  "brands_or_product_names": "",
  "unique_identifiers": "",
  "safety_gear": "",
  "weapon_type": "",
  "vehicle_type_or_model": "",
  "unusual_objects": "",
  "animals_seen": "",
  "activity_signs": "",
  "time_displayed": "",
  "image_quality": "",
  "visual_style": "",
  "filters_or_watermarks": "",
  "geo_clues": "",
  "primary_language_seen": "",
  "regional_indicators": "",
  "slang_or_dialect_detected": "",
  "cultural_or_religious_signs": "",
  "group_affiliations": "",
  "flags_uniforms_gestures": "",
  "deception_signs": "",
  "hashtags_or_keywords": "",
  "geo_political_relevance": "",
  "game_detected": false,
  "game_name": "",
  "exif_device": "",
  "watermark_found": false,
  "original_image_source": "",
  "poster_intent": "",
  "target_audience": "",
  "engagement_tricks": "",
  "psychological_triggers": "",
  "radical_language_or_symbols": "",
  "call_to_action": "",
  "recruiting_or_polarizing_content": "",
  "misinfo_or_agenda_signals": "",
  "summary_type": "",
  "key_takeaways": "",
  "cultural_or_geo_significance": "",
  "poster_purpose": "",
  "osint_value": "",
  "confidence_in_analysis": ""
}
  </code></pre>
</details>


#### Semantic Search Fields
| Property                    | Type | Description                         |
| --------------------------- | ---- | ----------------------------------- |
| **caption\_vector**         | LIST | Vector embedding of caption text for semantic search..   |
| **title\_vector**           | LIST | Vector embedding of title text for semantic search..     |
| **post\_analysis\_vector**  | LIST | Vector embedding of post analysis for semantic search..  |
| **image\_analysis\_vector** | LIST | Vector embedding of image analysis for semantic search.. |

</details>

### 💬 Comment - Represents a comment on a post.

<details>
<summary>See all properties</summary>
   
| Property             | Type       | Description                             |
| -------------------- | ---------- | --------------------------------------- |
| **id**               | INTEGER    | Unique identifier for the comment node. |
| **text**             | STRING     | Comment text.                           |
| **likes\_count**     | INTEGER    | Number of likes on the comment.         |
| **created\_at\_utc** | DATE\_TIME | UTC timestamp of comment creation.      |

#### Semantic Search Fields
| Property         | Type | Description                                           |
| ---------------- | ---- | ----------------------------------------------------- |
| **text\_vector** | LIST | Vector embedding of comment text for semantic search. |

</details>


### 🕸 Relationships

| Relationship                            | Description                                  |
| --------------------------------------- | -------------------------------------------- |
| 👤 Person - **Follows** -> 👤 Person    | A person **follows** another person.         |
| 👤 Person - **Posted** -> 📷 Post       | A person **created** the post.               |
| 👤 Person - **Liked** -> 📷 Post        | A person **liked** a specific post.          |
| 👤 Person - **Commented** -> 💬 Comment | A person **authored** the comment.           |
| 💬 Comment - **On** -> 📷 Post          | The comment is **made on** a specific post.  |
| 💬 Comment - **Reply To** -> 💬 Comment | A comment is a **reply to** another comment. |
| 👤 Person - **Liked** -> 💬 Comment     | A person **liked** a comment.                |


## 🕵 OSINTGraph AI Agent – Getting Started Guide
The OSINTGraph Agent helps you **explore, retrieve, and analyze your OSINT data in Neo4j.**
It works in two main ways:

- **Data Retrieval & Simple Analysis** – Fetch accounts, posts, comments, and relationships using filters, graph queries, and searches. You can also ask for quick insights (summaries, counts, highlights) on the retrieved data.

- **Template-Based Analysis** – For deeper investigations, use pre-built or custom templates. Templates guide the agent to retrieve the right data and apply structured analysis for more controlled , focused, and repeatable investigations.

This guide shows the two main ways to interact with the OSINTGraph AI Agent - **Data Retrieval** for quick questions, and **Template-Based Analysis** for deeper investigations. It also explains how to ask clear questions so you get the most accurate results.

> [!NOTE]
> These example questions are just a guide — you can ask the agent in your own words, and it will understand.


### 1. 🔧 Data Retrieval
Data Retrieval is best for **direct queries** and **simple analyses questions**
You can use it to fetch data based on **filters**, **relationships**, or **searches**.

#### Approach 1: Basic Data Retrieval  
Get data by filtering on straightforward criteria (e.g., usernames or dates).

**Example:**  
- “Get John’s comments from 2025”  
  *(Returns all comments made by John during 2025)*

- “How many comments has John made in 2025”  
  *(Returns the total number of comments John made during 2025)*

---

#### Approach 2: Relationship Traversal  
Include social connections in your query — followers, likers, commenters, etc.

**Example:**  
- “Find followers of John who commented on his posts in 2025”  
  *(Returns users who follow John and commented on his posts during 2025)*

---

#### Approach 3: Content Search

You can search data using two methods:

- **Keyword Search (literal word match):**
  Finds exact matches of words or phrases.  
  *Example:* “Find John’s comments from 2025 with the word ‘conference’”  
  *(Returns John’s 2025 comments containing the exact word “conference”)*

- **Semantic Search (meaning-based):**
  Finds content based on related meanings, including synonyms or related terms.
  
   Supported fields include:

   - Person: `username`, `fullname`, `bio`, `account_analysis`
   
   - Post: `caption`, `title`, `post_analysis`, `image_analysis`
   
   - Comment: `text`
     
  *Example:* “Show John’s comments from 2025 about startups”  
  *(Returns John’s 2025 comments'text related to “startups,” such as “new companies” or “ventures”)*

---

#### Combining Approaches
You can mix filters, relationships, and content search for precise results:

- “Find followers of John who liked his posts about startups in 2025”

> - Filters posts by date (2025)  
> - Traverses relationships to get John’s followers who liked those posts  
> - Apply semantic search on post content to find those about startups  

- “Find followers of John who liked his posts with the word ‘conference’ in 2025”  
> - Filters posts by date (2025)  
> - Traverses relationships to get John’s followers who liked those posts  
> - Apply keyword search on post content for the exact word “conference”

--- 

### 🎯 Best Practices – How to Ask Questions for Best Results

Being precise makes your results more accurate and useful. Here are key ways to improve your queries:

**Examples of precision:**

#### Precision in Searching Method  
- **Vague:** "Find posts about aura farming"  
- **Precise:** "**Use semantic search**, find posts about aura farming."

#### Precision in Targeting Data Fields  
- **Vague:** "Search for aura farming"  
- **Precise:** "Use semantic search on **post captions** about aura farming."

#### Precision in Context and Entities  
- **Vague:** "Where is John?"  
- **Precise:** "Which location might John be at **based on post captions, post analysis, and person bio**?"

#### Precision in Getting Results  
- **Vague:** "Tell me about John"  
- **Precise:** "Give John’s account analysis and follower count."

💡 **Tip:** When asking, think about:  
- What searching method should be applied if needed? (semantic search, keyword search)  
- Which data fields should be checked? (person bio, post analysis, post captions, etc.)  
- What exactly do you want back? (summary, detailed context, related entities, relationships, etc.)

This will speed up your investigation and ensure the Agent looks in the right places.

---

### 2. 🧩 Template-Based Analysis

Templates are **blueprints that tell the AI how to analyze your data**. Instead of manually going through posts, comments, likes, and social connections—which can take days—a template lets the OSINTGraph agent **gather all the needed data, feed it into a fresh AI, and get clear answers**.

**Example scenario:** You want to figure out where a person might be located. Doing it manually would take hours or days—looking through every post, comment, and followee. With a template, the AI can **analyze all this data** and **summarize likely locations**, saving you time and effort.

Each template run:

- Spawns a **new AI instance** with no memory of previous runs.

- Uses a **system prompt** (the AI’s “brain”) to guide reasoning.

- Injects the gathered data into a **user prompt** for analysis.

Templates are great because they let you:

1. **Control** how the AI thinks and reasons.

2. **Get consistent, repeatable results.**

3. **Analyze large datasets quickly** without doing manual work.

4. **Reuse the same template** across different targets or investigations.


### 📝 Template Structure

Templates are written as `.yaml` files with the following structure:

```yaml
name: <unique_template_name>
# Example: liked_post_analysis
# A unique identifier for the template. Used to select and run this template.

description: |
  <Brief explanation of what the template does, what kind of data it processes, and the type of output it produces.>
  # Example:
  #    Analyze liked posts to infer user interests and personality traits.

input_fields:
  # List of placeholders that will be replaced by actual data when running the template.
  # Each field defines a unique placeholder name and what data should be injected by OSINTGraph agent into that placeholder.
  - name: placeholder1
    description: |
      <Explain clearly what data this field should contain, and the exact format required.>
      # The agent will read these descriptions to automatically choose the correct Cypher queries, run them, and inject the results in the requested format.
      # Example:
      #    Provide User profile info including Person.username and Person.bio.
      #    Give results in this format:
      #       Username: ...
      #       Bio: ...

  - name: placeholder2
    description: |
      <Explain what this second input field should contain and its format.>
      # Describe what kind of data should be injected into this second placeholder when the template runs.
      # Example:
      #    A list of posts liked by the user, each with Post.caption and Post.post_analysis.
      #    Format in this way:
      #    Post:
      #       Catpion: ...
      #       Post analysis: ...     

system_prompt: |
  <Instructions defining the AI’s role, behavior, reasoning style, and output format>
  # Defines the LLM style, tone, rules, how to reason, what to infer, and how to format results
  # Example:
  #   You are a social media analyst. Review the user's liked posts and infer behavioral patterns or thematic interests based on post content.

user_prompt: |
  <Task description with placeholders for injected data>
  # The task request, with special placeholders `{placeholders}` for injected data
  # Example:
  #    Analyze the following profile and liked posts:
  #    Profile Info:
  #    {placeholder1}
  #
  #    Posts liked by the user:
  #    {placeholder2}
```

See an example template here: [location_analysis.yaml](https://github.com/XD-MHLOO/osintgraph-templates/blob/main/templates/location_analysis.yaml)

### 📦 Predefined Templates

OSINTGraph comes with several ready-to-use templates that cover common OSINT investigations. You can run them immediately without creating your own.

Examples include:

- **location_analysis** – Determine possible locations of the target user by analyzing posts, comments, likes, and their social graph.

- **contact_info_extraction** – Scan bios, captions, comments, and images for potential leaks of emails, phone numbers, or addresses.

- **interests_hobbies_lifestyle_analysis** – Uncover the target user’s interests, hobbies, and lifestyle preferences with supporting evidence from posts, likes, and network connections.

All predefined templates are maintained in this repository: https://github.com/XD-MHLOO/osintgraph-templates

**👉 To see the full list of predefined templates**:

  Ask the agent to list all templates in the folder. 

  > "list all templates"

**👉 To view details of a specific one:**

  Ask the agent to show a template by name, or you can view the YAML file directly in your templates folder (`osintgraph -h` to see the folder path).

  > "show template location_analysis"

**👉 To run a predefined template:**  
Ask the agent to execute the template.

> "Run location_analysis on target_username"


### ⚡ How Templates Work

1. **You request a template to run**  
    Example template with required additional context (e.g., username):  

   > "Run location_analysis template on JohnDoe"

   Choose the template you want to run and provide the agent with any required context.
  
   If you're not sure what to provide, simply ask the agent(e.g. "How to use \<the template\>") — it will guide you.

2. **Agent collects required data automatically**

   Based on the template’s input field descriptions, the agent automatically runs Cypher queries on your Neo4j database. It retrieves all required fields, formats the results, and fills the `{placeholders}` in the template's user prompt.

3. **Run Template and Get Output**

   A new LLM instance is created internally, using the template’s system and user prompts to analyze the data, then returns the output (e.g., analysis, summaries, or explanations) depending on the template's system prompt.

> [!NOTE]  
> OSINTGraph is primarily built using free services (e.g. Gemini API), therefore template runs are **rate-limited internally** to ensure stability.

### 🛠 How to Create Your Own Custom Template

**You can create a custom template by defining a `.yaml` file that controls how the AI analyzes your data.**

#### 🧠 Example Use Case

Let’s say you want to analyze a user's **bio**, **post captions**, and **comment texts** to extract any possible of contact details (such as emails, phone numbers, addresses, etc.) You can build a custom template like this:

```yaml
name: contact_info_extraction

description: |
  Analyze a user's profile bio, post captions, comment texts and image analysis
  (OCR and visual text) to detect any possible leaks of contact details such as emails, phone numbers, or addresses, and return them in a structured Markdown list with supporting context.

input_fields:
  - name: bio
    description: |
      The user’s Person.bio.

      Format:
      Bio:
        Text: ...

  - name: posts
    description: |
      List of all posts made by the user. Each post must include:
        - Post.shortcode
        - Post.caption
        - Post.image_analysis

      Format (One post per entry):
        User Post:
          Post Url: https://www.instagram.com/p/<Post.shortcode>/
          Caption: ...
          Image Analysis:

          Image 1:
          - People: [...]
          - Text/OCR: [...]
          - Summary: [...]

          Image 2:
          ...

  - name: comments
    description: |
      A list of Comment.text authored by the user.

      Format:
      Comment:
        Text: ...

system_prompt: |
  You are a digital privacy analyst. Your task is to carefully analyze the provided data to identify any possible leaks of contact details, including but not limited to:
  - Email addresses
  - Phone numbers
  - Addresses
  - Social media handles, usernames, or IDs
  - Any other identifiers that may reveal contact information
  - Use pattern recognition and contextual reasoning to flag potential contact details.
  - If detected, report each type of possible contact detail (email, phone, address, ..) in a structured Markdown format.
  - For each match, include:
    - The type of contact detail (Email, Phone, Address, etc.)
    - The exact string detected
    - The source field (bio, caption, comment, image OCR) (cite Post Url for Post image OCR )
    - Context / Possible Use — Based on surrounding information, what the contact might be
    - A brief reasoning (if the match is inferred and not explicit)
    - A confidence level (High / Medium / Low), with justification for the confidence
  - If nothing is found, return: "No possible contact details detected."

user_prompt: |
  Review the following content and extract any possible contact-related information:
  
  User Bio:
  {bio}
  
  List of User Posts:
  {posts}
  
  List of User Comments:
  {comments}


```
**Steps to Create Your Template**

1. `name`
Choose a unique name to identify your template. This will be used to select and run the template.

2. `description`
Briefly describe what your template does and the kind of output it produces.
   > This helps the OSINTGraph agent better understand the intent and use of the template.

3. `input_fields`
Define what data the agent should inject at runtime. Each input field includes:

- `name`: Used as `{placeholder}` in the user prompt.

- `description`: Explain exactly what data should be injected here and how it should be formatted.

> [!NOTE]
> - For direct schema attributes (e.g., `Person.bio`, `Post.caption`), mention them explicitly so the agent knows to fetch them directly from the database.

4. `System Prompt`
Write clear instructions defining the AI’s role, behavior, how to reason, and how to format its output. This controls how the AI thinks and processes the data.

5. `User Prompt`
Write the actual task description, with `{placeholder_name}` tags for runtime data injection.


#### 📂 Add Your Custom Template

1. Place your custom `.yaml` template file into your templates folder.
(Run osintgraph -h to see where the folder is located.)

2. Validate Your Template:
   
   > "list all templates including invalid ones"
   
   The agent will display all templates in the folder. If your custom template has errors, it will show where; if no errors appear, your template is valid and ready to use. (No need to restart `osintgraph agent` if it’s already running — simply ask to "refresh and list all templates" again.)

## 🚫 **How to Avoid Account Suspension**

1. <mark>**Use Your Browser Session**</mark>  
   When running `osintgraph setup instagram`, choose login via Firefox session to make the login look natural. 🌐

2. <mark>**Use Your Real User-Agent**</mark>  
   When running `osingraph setup user-agent`, provide the exact user-agent from the browser you use to log in to your Instagram account. 🖥️

3. <mark>**Enable 2FA**</mark>  
   Turn on 2FA for your Instagram account. It’s simple: just use an authenticator app, and it helps Instagram recognize that your account is legitimate. 🔒

4. <mark>**Build Account Reputation**</mark>  
   Use your Instagram account normally (like posts, comment, watch stories) for a few days or weeks before scraping. 📈

5. <mark>**Warm Up Your Session**</mark>  
   Spend time using Instagram before scraping, like a normal user, to avoid looking suspicious. ⏳

6. **Avoid VPNs**  
   Don’t use VPNs. Instagram may flag accounts with mismatched or suspicious locations. 🚫🌍

7. **Don’t Use the Account for Other Activities While Scraping**  
   When using this tool to collect data, avoid using the same Instagram account for any other activities. 🛑

8. **Limit Scraping Time**  
   Don’t scrape for more than 6 hours straight. ⏰
### Credit:  
- Thanks to [@ahmdrz](https://github.com/ahmdrz) for these valuable insights on avoiding account suspension. 🙏
- Also see [this useful comment](https://github.com/instaloader/instaloader/issues/2391#issuecomment-2400987481) on Instaloader's GitHub for more tips.

---

## 📦 Dependencies:
- **[Instaloader](https://github.com/instaloader/instaloader)** – Used to collect Instagram profile data, followers, and followees.
- **[Neo4j](https://neo4j.com/)** – Graph database used to store and visualize the Instagram social network.
- **[LangGraph](https://github.com/langchain-ai/langgraph)** – Handles structured multi-step LLM reasoning and ReAct-style agent execution.
- **[Gemini / Google Generative AI](https://developers.google.com/)** – Provides the LLM model used for AI-powered analysis and powers the AI agent.

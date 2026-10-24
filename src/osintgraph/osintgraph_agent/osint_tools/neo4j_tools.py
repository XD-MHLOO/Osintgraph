import json
from langchain.tools import StructuredTool
from langchain_core.tools import Tool
from ...utils.schemas import SemanticCypherInput
from ...services import llm_models

def build_cypher_query_tool(nm):
    def cypher_query_tool(query: str):
        
            try:
                result = nm.execute_read(nm.run_cypher_query, query)
                return json.dumps(result, indent=2)
            
            except TypeError as e:
                if "DateTime" in str(e):
                    return "Error: DateTime must be wrapped with toString(). Retry the query with toString()."
                return f"Error: {str(e)}"
            except Exception as e:
                    return f"Cypher execution failed: {str(e)}"
            
    return Tool.from_function(
        func=cypher_query_tool,
        name="cypher_query_tool",
        description= """
            Executes a Cypher query on the Neo4j database for general data retrieval.

This tool supports:
1. Standard Cypher queries for graph traversal, node attributes, and relationships.
2. Filtering by usernames, post shortcodes, dates, keywords, and other criteria.

Use this tool to:
- Retrieve raw information from the graph (specific node properties or relationships).
- Gather structured data for templates or analysis.
- Apply keyword searches only when relevant; its primary purpose is data retrieval.

-------------------------------------------------------

🚫 Guidelines:
- NEVER return entire nodes or all fields with wildcards (e.g., `RETURN p {.*}` or `RETURN p`).
- ALWAYS explicitly return only the fields required.
- Wrap DateTime fields with `toString()` for JSON serialization.
- Avoid returning vector embeddings or internal system fields unless explicitly requested.

Examples:
RETURN p.username, p.fullname
RETURN post.shortcode, post.caption, toString(post.date_utc) AS date_utc
RETURN comment.text, toString(comment.created_at_utc) AS created_at

Analysis Fields:
- Person nodes: `account_analysis` can be returned.
- Post nodes: `post_analysis` can be returned.
- Image analysis (`image_analysis`) only if explicitly requested.

Args:
    query (str): A raw Cypher query string.
        Example: "MATCH (p:Person) RETURN p.username, p.bio"

Returns:
    str: Result of the Cypher query as structured output (JSON).

-----------------------------------------------
Example — Find John’s posts mentioning “crypto” with >5 likes, liked by his followers:
MATCH 
    (john:Person {username: "john"})<-[:FOLLOWS]-(follower:Person),
    (follower)-[:LIKED]->(post:Post)<-[:POSTED]-(john)
WHERE 
    post.caption CONTAINS "crypto" AND post.likes > 5
RETURN 
    post.shortcode AS shortcode, 
    toString(post.date_utc) AS date_utc, 
    post.caption AS caption,
    follower.username AS follower_username

Example — Find comments by users who follow Jane on posts in 2024 containing "urgent":
MATCH 
    (jane:Person {username: "jane"})<-[:FOLLOWS]-(follower:Person),
    (jane)-[:POSTED]->(post:Post),
    (follower)-[:COMMENTED]->(comment:Comment)-[:ON]->(post)
WHERE 
    comment.text CONTAINS "urgent" AND
    post.date_utc >= date("2024-01-01") AND
    post.date_utc < date("2025-01-01") AND
    post.likes > 10
RETURN 
    comment.text AS comment, 
    toString(comment.created_at_utc) AS created_at, 
    follower.username AS commenter_username, 
    post.shortcode AS post_shortcode
ORDER BY comment.created_at_utc DESC

- Use keyword filtering only when needed (e.g., CONTAINS, approximate matches). Primary focus is structured data retrieval.
"""
    )


def build_semantic_cypher_tool(nm):
    def semantic_cypher_tool(query_text: str, cypher_template: str):
        embeddings = llm_models.get_embeddings_model()
        if embeddings is None:
            return "Error: no embeddings provider is configured; semantic search is unavailable."
        vector = embeddings.embed_query(query_text)

        try:
            result = nm.execute_read(nm.run_cypher_query, cypher_template, vector)
            return json.dumps(result, indent=2)
    
        except TypeError as e:
            if "DateTime" in str(e):
                return "Error: DateTime must be wrapped with toString(). Retry the query with toString()."
            return f"Error: {str(e)}"
        except Exception as e:
                return f"Cypher execution failed: {str(e)}"



    return StructuredTool.from_function(
        func=semantic_cypher_tool,
        name="semantic_cypher_tool",
        args_schema=SemanticCypherInput,
        description="""
## Semantic Search Tool Documentation (Fully Organized & Clear)

### Overview

Performs semantic (vector-based) searches in Neo4j using a keyword or phrase and a Cypher query.

- **Purpose**: Surface potentially relevant results based on semantic meaning. Validation against user intent is required.
- **Inputs**:
  - `query_text` (string): phrase to embed as vector
  - `cypher_template` (string): Cypher query with `$vector` placeholder only
- **Automatically**:
  1. Embeds `query_text` to a vector
  2. Injects `$vector` into the Cypher query
  3. Runs the query and returns results

---

### Inputs

- `query_text`: concise keyword/phrase representing the intended meaning.
  - Example: "supportive tone", "protest activity", "drug trafficking"
- `cypher_template`: complete Cypher query containing `$vector` placeholder

---

### Semantic Search Types

1. **General Semantic Search**
   - No specific node filtering.
   - Search across the entire dataset.
   - Default: retrieve 3 batches (100 + 100 + 100 = 300 results)
   - Extended: continue in additional batches up to 1000 results if user requests deeper search.

2. **Filtered Semantic Search**
   - Restrict search to a subset of nodes (e.g., posts by a user, liked content).
   - Default: 1 batch of 100 results.
   - Extended: if user requests deeper/broader search, lower similarity threshold (e.g., 0.75 → 0.6) and continue batching using SKIP/LIMIT.

---

### Vector Indexes and Properties

**General Search (Vector Indexes)**

- Format: `{{node_type}}_{{field}}_vector_index`
- Person: `person_bio_vector_index`
- Post: `post_post_analysis_vector_index`
- Comment: `comment_text_vector_index`

**Filtered Search (Direct Vector Properties)**

- Person: username_vector, fullname_vector, bio_vector, account_analysis_vector
- Post: caption_vector, title_vector, image_analysis_vector, post_analysis_vector
- Comment: text_vector

---

### Search Steps

#### Step 1: Identify Relevant Keywords

- Extract meaningful keywords from user query.
- Example:
  - Query: "Looking for comments about climate change activism"
  - Keywords: `comments`, `climate change`, `activism`

#### Step 2: Choose the Correct Vector Index

- **General Search**: use appropriate vector index.
- **Filtered Search**: use Cypher MATCH/WHERE and vector.similarity.cosine() on direct vector properties.

#### Step 3: Run Semantic Search

**General Search Example (3 batches)**

```cypher
// Batch 1
CALL db.index.vector.queryNodes('comment_text_vector_index', 100, $vector)
YIELD node, score
RETURN node.text AS text, toString(node.created_at_utc) AS created_at_utc, score
ORDER BY score DESC
SKIP 0
LIMIT 100

// Batch 2
CALL db.index.vector.queryNodes('comment_text_vector_index', 100, $vector)
YIELD node, score
RETURN node.text AS text, toString(node.created_at_utc) AS created_at_utc, score
ORDER BY score DESC
SKIP 100
LIMIT 100

// Batch 3
CALL db.index.vector.queryNodes('comment_text_vector_index', 100, $vector)
YIELD node, score
RETURN node.text AS text, toString(node.created_at_utc) AS created_at_utc, score
ORDER BY score DESC
SKIP 200
LIMIT 100
```

- Continue in additional batches of 100 if user requests deeper search, up to 1000 results.

**Filtered Search Example (default 100)**

```cypher
MATCH (:Person {username: "john"})-[:COMMENTED]->(comment)
WITH comment, vector.similarity.cosine(comment.text_vector, $vector) AS score
WHERE score > 0.75
RETURN comment.text AS text, score
ORDER BY score DESC
LIMIT 100
```

- Continue batching only if user requests broader/deeper search.
- Adjust similarity threshold as needed (e.g., 0.75 → 0.6).

#### Step 4: Analyze Results

- Include only results that clearly match user intent.
- Exclude ambiguous or loosely related content.
- Scores are for ranking only.

#### Step 5: Stop Conditions

- **General Search**: default 300 results; extend to 1000 if user asks.
- **Filtered Search**: default 100 results; extend with lower similarity threshold and batching if user asks.

---

### Output Rules

- Never return all fields or entire nodes.
- Always explicitly specify fields.
- Wrap DateTime fields with `toString()`.
- Do not return vector embeddings unless explicitly requested.
- Analysis fields: `account_analysis` for Person, `post_analysis` for Post, `image_analysis` only if requested.

---

### Summary of Defaults & Extended Behavior

| Search Type     | Default Retrieval     | Extended Retrieval                                                                     |
| --------------- | --------------------- | -------------------------------------------------------------------------------------- |
| General Search  | 3 batches × 100 = 300 | Up to 1000 results (additional batches of 100)                                         |
| Filtered Search | 1 batch × 100         | Continue with lower similarity threshold and SKIP/LIMIT batching if user requests more |


"""
    )
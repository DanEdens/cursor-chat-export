import os
import sqlite3
import yaml
import json
from typing import Any
from loguru import logger

class VSCDBQuery:
    def __init__(self, db_path: str) -> None:
        """
        Initialize the VSCDBQuery with the path to the SQLite database.

        Args:
            db_path (str): The path to the SQLite database file.
        """
        self.db_path = db_path
        logger.info(f"Database path: {os.path.join(os.path.basename(os.path.dirname(self.db_path)), os.path.basename(self.db_path))}")

    def query_to_json(self, query: str) -> list[Any] | dict[str, str]:
        """Execute a SQL query and return the results.

        Args:
            query (str): The SQL query to execute.

        Returns:
            list[Any] | dict[str, str]: The query results as a list, or an error message as a dictionary.
        """
        try:
            logger.debug(f"Executing query: {query}")
            conn = sqlite3.connect(f'file:{self.db_path}?mode=ro', uri=True)
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()

            # Return full rows instead of just first column
            result = rows
            logger.success(f"Query executed successfully, fetched {len(result)} rows.")
            return result
        except sqlite3.Error as e:
            logger.error(f"SQLite error: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {"error": str(e)}

    def query_aichat_data(self) -> list[Any] | dict[str, str]:
        """Query the AI chat data from the database."""
        try:
            with open('config.yml', 'r') as config_file:
                config = yaml.safe_load(config_file)
            query = config['aichat_query']
            logger.debug("Loaded AI chat query from config.yaml")
            
            # Get data from ItemTable
            results = self.query_to_json(query)
            
            # Also query cursorDiskKV table
            try:
                conn = sqlite3.connect(f'file:{self.db_path}?mode=ro', uri=True)
                cursor = conn.cursor()
                cursor.execute("SELECT key, value FROM cursorDiskKV")
                kv_rows = cursor.fetchall()
                conn.close()
                
                # Add cursorDiskKV results
                results.extend(kv_rows)
                
            except sqlite3.Error as e:
                logger.debug(f"Note: cursorDiskKV table not found or not accessible: {e}")
            
            # Log the structure of each result
            for key, value in results:
                try:
                    data = json.loads(value)
                    logger.debug(f"Processing key: {key}")
                    if isinstance(data, dict):
                        logger.debug(f"Keys: {list(data.keys())}")
                        logger.debug(f"Sample: {json.dumps(data, indent=2)[:500]}...")
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    logger.debug(f"Error processing {key}: {e}")

            return results
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {"error": str(e)}

    def list_tables(self) -> list[str]:
        """List all tables in the database.
        
        Returns:
            list[str]: List of table names
        """
        try:
            conn = sqlite3.connect(f'file:{self.db_path}?mode=ro', uri=True)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            conn.close()
            logger.info("Available tables:")
            for table in tables:
                logger.info(f"  - {table[0]}")
            return [table[0] for table in tables]
        except Exception as e:
            logger.error(f"Error listing tables: {e}")
            return []

    def inspect_table(self, table_name: str, limit: int = 5) -> None:
        """Inspect the contents of a table."""
        try:
            conn = sqlite3.connect(f'file:{self.db_path}?mode=ro', uri=True)
            cursor = conn.cursor()

            # Get column names
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            logger.info(f"\nColumns in {table_name}:")
            for col in columns:
                logger.info(f"  - {col[1]} ({col[2]})")

            if table_name == 'ItemTable':
                # List all keys
                cursor.execute("""
                    SELECT [key]
                    FROM ItemTable
                    ORDER BY [key]
                """)
                keys = cursor.fetchall()
                logger.info("\nAll keys in ItemTable:")
                for key in keys:
                    logger.info(f"  - {key[0]}")

                # Look for potential chat-related content with broader search
                cursor.execute("""
                    SELECT [key], substr(value, 1, 100) as preview 
                    FROM ItemTable 
                    WHERE [key] LIKE '%chat%' 
                       OR [key] LIKE '%composer%'
                       OR [key] LIKE '%conversation%'
                       OR [key] LIKE '%copilot%'
                       OR [key] LIKE '%message%'
                       OR [key] LIKE '%history%'
                       OR [key] LIKE '%ai%'
                       OR [key] LIKE '%assistant%'
                """)
                chat_rows = cursor.fetchall()
                if chat_rows:
                    logger.info("\nPotentially relevant entries found:")
                    for key, preview in chat_rows:
                        logger.info(f"  Key: {key}")
                        logger.info(f"  Preview: {preview}...")
                        logger.info("  ---")

            conn.close()
        except Exception as e:
            logger.error(f"Error inspecting table {table_name}: {e}")

    def find_db_files(self) -> list[str]:
        """Find all potential database files in the workspace directory."""
        db_dir = os.path.dirname(self.db_path)
        db_files = []

        for file in os.listdir(db_dir):
            if file.endswith('.vscdb') or file.endswith('.db'):
                full_path = os.path.join(db_dir, file)
                logger.info(f"Found database file: {file}")
                db_files.append(full_path)

        return db_files

    def inspect_key(self, key: str) -> None:
        """Inspect the full contents of a specific key."""
        try:
            conn = sqlite3.connect(f'file:{self.db_path}?mode=ro', uri=True)
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM ItemTable WHERE [key] = ?", (key,))
            row = cursor.fetchone()
            conn.close()

            if row:
                try:
                    data = json.loads(row[0])
                    logger.info(f"\nFull contents of {key}:")
                    if isinstance(data, dict):
                        logger.info(f"Keys: {list(data.keys())}")
                        for k, v in data.items():
                            logger.info(f"\n{k}:")
                            logger.info(f"{json.dumps(v, indent=2)[:1000]}...")
                    elif isinstance(data, list):
                        logger.info(f"List with {len(data)} items")
                        for item in data[:5]:  # Show first 5 items
                            logger.info(f"\nItem:")
                            logger.info(f"{json.dumps(item, indent=2)[:1000]}...")
                except json.JSONDecodeError:
                    logger.info(f"Raw value: {row[0][:1000]}...")
        except Exception as e:
            logger.error(f"Error inspecting key {key}: {e}")

    def inspect_composer(self, composer_id: str) -> None:
        """Inspect all data related to a specific composer ID."""
        try:
            conn = sqlite3.connect(f'file:{self.db_path}?mode=ro', uri=True)
            cursor = conn.cursor()
            
            # First get all generations to find their UUIDs
            cursor.execute("SELECT value FROM ItemTable WHERE [key] = 'aiService.generations'")
            row = cursor.fetchone()
            generation_uuids = []
            if row:
                try:
                    generations = json.loads(row[0])
                    if isinstance(generations, list):
                        for gen in generations:
                            if isinstance(gen, dict) and 'generationUUID' in gen:
                                generation_uuids.append(gen['generationUUID'])
                                logger.debug(f"Found generation UUID: {gen['generationUUID']}")
                except json.JSONDecodeError:
                    pass

            # Now search for responses in cursorDiskKV table
            cursor.execute("SELECT key, value FROM cursorDiskKV")
            responses = cursor.fetchall()
            for key, value in responses:
                try:
                    data = json.loads(value)
                    if isinstance(data, dict) and 'response' in data:
                        logger.info(f"\nFound response in cursorDiskKV key {key}:")
                        logger.info(json.dumps(data, indent=2))
                except json.JSONDecodeError:
                    continue

            # Also get the prompts
            cursor.execute("SELECT value FROM ItemTable WHERE [key] = 'aiService.prompts'")
            row = cursor.fetchone()
            if row:
                try:
                    prompts = json.loads(row[0])
                    if isinstance(prompts, list):
                        logger.info("\nPrompts:")
                        for prompt in prompts:
                            if isinstance(prompt, dict):
                                if 'text' in prompt:
                                    logger.info(f"- Text: {prompt['text']}")
                                if 'generationUUID' in prompt:
                                    logger.info(f"  UUID: {prompt['generationUUID']}")
                except json.JSONDecodeError:
                    pass

            conn.close()
        except Exception as e:
            logger.error(f"Error inspecting composer {composer_id}: {e}")

# Example usage:
# db_query = VSCDBQuery('/Users/somogyijanos/Library/Application Support/Cursor/User/workspaceStorage/b989572f2e2186b48b808da2da437416/state.vscdb')
# json_result = db_query.query_to_json("SELECT value FROM ItemTable WHERE [key] IN ('workbench.panel.aichat.view.aichat.chatdata');")
# print(json_result)

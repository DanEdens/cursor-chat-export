import re
import shutil
import os
import json
from abc import ABC, abstractmethod
from typing import Any
from loguru import logger
import traceback

class ChatFormatter(ABC):
    @abstractmethod
    def format(self, chat_data: dict[str, Any], image_dir: str = 'images') -> dict[int, str] | None:
        """Format the chat data into Markdown format.

        Args:
            chat_data (dict[str, Any]): The chat data to format.
            image_dir (str): The directory where images will be saved. Defaults to 'images'.

        Returns:
            dict[int, str]: The formatted chat for each tab.
        """
        pass

class MarkdownChatFormatter(ChatFormatter):
    def _extract_text_from_user_bubble(self, bubble: dict) -> str:
        try:
            if "delegate" in bubble:
                if bubble["delegate"]:
                    user_text_text = bubble['delegate']["a"]
                else:
                    user_text_text = ""
            elif "text" in bubble:
                if bubble["text"]:
                    user_text_text = bubble['text']
                else:
                    user_text_text = ""
            elif "initText" in bubble:
                if bubble["initText"]:
                    try:
                        user_text_text = json.loads(bubble["initText"])['root']['children'][0]['children'][0]['text']
                    except Exception as e:
                        user_text_text = "[ERROR: no user text found]"
                        logger.error(f"Couldn't find user text entry in one of the bubbles. Error: {e}")
                        logger.debug(f"Bubble:\n{json.dumps(bubble, indent=4)}")
                else:
                    user_text_text = ""
            elif "rawText" in bubble:
                if bubble["rawText"]:
                    user_text_text = bubble['text']
                else:
                    user_text_text = ""
            else:
                user_text_text = "[ERROR: no user text found]"
                logger.error(f"Couldn't find user text entry in one of the bubbles.")
                logger.debug(f"Bubble:\n{json.dumps(bubble, indent=4)}")

        except Exception as e:
            user_text_text = "[ERROR: no user text found]"
            logger.error(f"Couldn't find user text entry in one of the bubbles. Error: {e}")
            logger.debug(f"Bubble:\n{json.dumps(bubble, indent=4)}")

        return user_text_text

    def _format_composer_data(self, composer_data: dict, generations: list, prompts: list, responses: list) -> str:
        """Format composer data including related generations and prompts."""
        formatted = []
        
        # Add composer metadata
        formatted.append(f"# {composer_data.get('name', 'Untitled Composer')}\n")
        formatted.append(f"Composer ID: {composer_data.get('composerId')}\n")
        formatted.append(f"Created: {composer_data.get('createdAt')}\n")
        formatted.append(f"Last Updated: {composer_data.get('lastUpdatedAt')}\n")
        formatted.append(f"Mode: {composer_data.get('unifiedMode', 'unknown')}\n\n")
        
        # Create a map of generation UUIDs to responses
        response_map = {}
        for key, value in responses:
            try:
                data = json.loads(value)
                if isinstance(data, dict) and 'response' in data:
                    # Try to extract UUID from key or look in data
                    uuid = data.get('generationUUID', key.split(':')[-1])
                    response_map[uuid] = data['response']
                    logger.debug(f"Found response for UUID {uuid}")
            except json.JSONDecodeError:
                continue
        
        # Add conversation history
        formatted.append("## Conversation\n")
        
        # Sort prompts by timestamp if available
        if prompts and isinstance(prompts[0], dict) and 'unixMs' in prompts[0]:
            prompts = sorted(prompts, key=lambda x: x.get('unixMs', 0))
        
        for prompt in prompts:
            if not isinstance(prompt, dict):
                continue
            
            # Add user message
            if 'text' in prompt:
                formatted.append("### User\n")
                formatted.append(f"{prompt['text']}\n\n")
            
            # Look for corresponding AI response
            if 'generationUUID' in prompt:
                uuid = prompt['generationUUID']
                logger.debug(f"Looking for response with UUID {uuid}")
                if uuid in response_map:
                    formatted.append("### Assistant\n")
                    formatted.append(f"{response_map[uuid]}\n\n")
                else:
                    # Look in generations for textDescription
                    for gen in generations:
                        if isinstance(gen, dict) and gen.get('generationUUID') == uuid:
                            if 'textDescription' in gen:
                                formatted.append("### Assistant\n")
                                formatted.append(f"{gen['textDescription']}\n\n")
                            break
        
        return "\n".join(formatted)

    def format(self, chat_data: list[tuple[str, str]], image_dir: str | None = 'images', tab_ids: list[int] | None = None) -> dict[int, str] | None:
        """Format the chat data into Markdown format.

        Args:
            chat_data (list[tuple[str, str]]): List of (key, value) tuples containing chat data.
            image_dir (str): The directory where images will be saved.
            tab_ids (list[int]): List of tab indices to include exclusively.

        Returns:
            dict[int, str]: The formatted chat in Markdown for each tab.
        """
        try:
            formatted_chats = {}
            chat_count = 0

            # First, collect all the data
            composer_data = None
            generations = []
            prompts = []
            responses = []

            for key, value in chat_data:
                try:
                    data = json.loads(value)
                    if not isinstance(data, (dict, list)):  # Skip if not dict or list
                        continue

                    if key == 'composer.composerData':
                        composer_data = data
                    elif key == 'aiService.generations':
                        generations = data if isinstance(data, list) else []
                    elif key == 'aiService.prompts':
                        prompts = data if isinstance(data, list) else []
                    elif key.startswith('cursorDiskKV:'):
                        responses.append((key, value))
                except json.JSONDecodeError:
                    continue

            # Handle composer data if available
            if composer_data and isinstance(composer_data, dict) and 'allComposers' in composer_data:
                for composer in composer_data['allComposers']:
                    chat_count += 1
                    formatted_chat = self._format_composer_data(composer, generations, prompts, responses)
                    if formatted_chat.strip():
                        formatted_chats[f"composer_{composer.get('composerId', chat_count)}"] = formatted_chat

            # Handle regular chat data
            for key, value in chat_data:
                try:
                    data = json.loads(value)
                    if not isinstance(data, dict):  # Skip if not a dict
                        continue

                    if 'tabs' in data:
                        for tab_index, tab in enumerate(data['tabs']):
                            if tab_ids is not None and tab_index not in tab_ids:
                                continue
                            formatted_chat = self._format_aichat_tab(tab, chat_count + 1, image_dir)
                            if formatted_chat.strip():
                                chat_count += 1
                                formatted_chats[f"chat_{chat_count}"] = formatted_chat
                except json.JSONDecodeError:
                    continue

            if formatted_chats:
                logger.success(f"Successfully formatted {len(formatted_chats)} chats.")
            else:
                logger.warning("No chat content found to format.")
            return formatted_chats
        except Exception as e:
            logger.error(f"Unexpected error: {e}. Full traceback: {traceback.format_exc()}")
            return None

    def _format_aichat_tab(self, tab: dict, index: int, image_dir: str | None) -> str:
        """Format a single AI chat tab."""
        formatted_chat = [f"# Chat Transcript - {tab.get('chatTitle', f'Chat {index}')}\n"]

        for bubble in tab['bubbles']:
            if bubble['type'] == 'user':
                formatted_chat.extend(self._format_user_bubble(bubble, index, image_dir))
            elif bubble['type'] == 'ai':
                formatted_chat.extend(self._format_ai_bubble(bubble))

        return "\n".join(formatted_chat)

    def _format_composer_chat(self, composer: dict, index: int) -> str:
        """Format a single composer chat."""
        # Skip empty or header-only composers
        if composer.get('type') == 'head' and not composer.get('messages'):
            return ""

        title = composer.get('name', composer.get('title', f'Chat {index}'))
        formatted_chat = [f"# Composer Chat - {title}\n"]

        # Handle different message formats
        if 'messages' in composer:
            for msg in composer['messages']:
                if msg.get('role') == 'user':
                    formatted_chat.append(f"## User:\n\n{msg.get('content', '')}\n")
                elif msg.get('role') == 'assistant':
                    formatted_chat.append(f"## AI ({msg.get('model', 'Unknown')}):\n\n{msg.get('content', '')}\n")
        elif 'chats' in composer:
            for chat in composer['chats']:
                formatted_chat.extend(self._format_chat_messages(chat))

        # Return empty string if no content was added
        if len(formatted_chat) <= 1:
            return ""

        return "\n".join(formatted_chat)

    def _format_chat_messages(self, chat: dict) -> list[str]:
        """Format messages from a chat."""
        formatted = []
        messages = chat.get('messages', [])
        for msg in messages:
            if msg.get('role') == 'user':
                formatted.append(f"## User:\n\n{msg.get('content', '')}\n")
            elif msg.get('role') == 'assistant':
                formatted.append(f"## AI ({msg.get('model', 'Unknown')}):\n\n{msg.get('content', '')}\n")
        return formatted

    def _format_user_bubble(self, bubble: dict, index: int, image_dir: str | None) -> list[str]:
        user_text = ["## User:\n\n"]

        # Selections
        if "selections" in bubble and bubble["selections"]:
            user_text.append(f"[selections]  \n{'\n'.join([s['text'] for s in bubble['selections']])}")

        # Images
        if 'image' in bubble and image_dir is not None:
            image_path = bubble['image']['path']
            if os.path.exists(image_path):
                image_filename = os.path.basename(image_path)
                new_image_path = os.path.join(tab_image_dir, image_filename)
                tab_image_dir = os.path.join(image_dir, f"tab_{index}") if image_dir else None
                if tab_image_dir is not None:
                    os.makedirs(tab_image_dir, exist_ok=True)
                shutil.copy(image_path, new_image_path)
                user_text.append(f"[image]  \n![User Image]({new_image_path})")
            else:
                logger.error(f"Image file {image_path} not found for tab {index}.")
                user_text.append(f"[image]  \n![User Image]()")

        # Text
        user_text_text = self._extract_text_from_user_bubble(bubble)
        if user_text_text:
            user_text.append(f"[text]  \n{user_text_text}")

        user_text.append("\n")

        if len(user_text) > 2:
            return user_text
        else:
            return []

    def _format_ai_bubble(self, bubble: dict) -> list[str]:
        model_type = bubble.get('modelType', 'Unknown')
        raw_text = re.sub(r'```python:[^\n]+', '```python', bubble['rawText'])
        return [f"## AI ({model_type}):\n\n{raw_text}\n"]

    def _format_history_entries(self, entries: list, index: int) -> str:
        """Format history entries into chat format."""
        formatted_chat = [f"# History Entries - {index}\n"]

        for entry in entries:
            if isinstance(entry, list) and len(entry) >= 2:
                # Handle Git history format
                if entry[0] == "Git":
                    formatted_chat.append(f"## Git Entry:\n\n```\n{json.dumps(entry[1], indent=2)}\n```\n")
            elif isinstance(entry, dict):
                # Handle other history entries
                if 'editor' in entry:
                    formatted_chat.append(f"## Editor Entry:\n\n```\n{json.dumps(entry['editor'], indent=2)}\n```\n")

        return "\n".join(formatted_chat) if len(formatted_chat) > 1 else ""

class FileSaver(ABC):
    @abstractmethod
    def save(self, formatted_data: str, file_path: str) -> None:
        """Save the formatted data to a file.

        Args:
            formatted_data (str): The formatted data to save.
            file_path (str): The path to the file where the data will be saved.
        """
        pass

class MarkdownFileSaver(FileSaver):
    def save(self, formatted_data: str, file_path: str) -> None:
        """Save the formatted data to a Markdown file.

        Args:
            formatted_data (str): The formatted data to save.
            file_path (str): The path to the Markdown file where the data will be saved.
        """
        try:
            with open(file_path, 'w') as file:
                file.write(formatted_data)
            logger.info(f"Chat has been formatted and saved as {file_path}")
        except IOError as e:
            logger.error(f"IOError: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

class ChatExporter:
    def __init__(self, formatter: ChatFormatter, saver: FileSaver) -> None:
        """Initialize the ChatExporter with a formatter and a saver.

        Args:
            formatter (ChatFormatter): The formatter to format the chat data.
            saver (FileSaver): The saver to save the formatted data.
        """
        self.formatter = formatter
        self.saver = saver

    def export(self, chat_data: list[tuple[str, str]], output_dir: str, image_dir: str, tab_ids: list[int] | None = None) -> None:
        """Export the chat data by formatting and saving it.

        Args:
            chat_data (list[tuple[str, str]]): List of (key, value) tuples containing chat data.
            output_dir (str): The directory where the formatted data will be saved.
            image_dir (str): The directory where images will be saved.
            tab_ids (list[int]): List of tab indices to include exclusively.
        """
        try:
            os.makedirs(output_dir, exist_ok=True)
            formatted_chats = self.formatter.format(chat_data, image_dir, tab_ids=tab_ids)
            if formatted_chats is not None:
                for chat_name, formatted_data in formatted_chats.items():
                    file_path = os.path.join(output_dir, f"{chat_name}.md")
                    self.saver.save(formatted_data, file_path)
        except Exception as e:
            logger.error(f"Failed to export chat data: {e}")

# Example usage:
# Load the chat data from the JSON file
# with open('chat.json', 'r') as file:
#     chat_data = json.load(file)

# formatter = MarkdownChatFormatter()
# saver = MarkdownFileSaver()
# exporter = ChatExporter(formatter, saver)
# exporter.export(chat_data, 'output_folder', 'images')

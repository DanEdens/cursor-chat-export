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

    def format(self, chat_data: list[str], image_dir: str | None = 'images', tab_ids: list[int] | None = None) -> dict[int, str] | None:
        """Format the chat data into Markdown format.

        Args:
            chat_data (list[str]): List of JSON strings containing chat data.
            image_dir (str): The directory where images will be saved.
            tab_ids (list[int]): List of tab indices to include exclusively.

        Returns:
            dict[int, str]: The formatted chat in Markdown for each tab.
        """
        try:
            formatted_chats = {}
            chat_count = 0

            for data_str in chat_data:
                data = json.loads(data_str)

                # Handle aichat data
                if 'tabs' in data:
                    for tab_index, tab in enumerate(data['tabs']):
                        if tab_ids is not None and tab_index not in tab_ids:
                            continue
                        formatted_chat = self._format_aichat_tab(tab, chat_count + 1, image_dir)
                        if formatted_chat.strip():  # Only include non-empty chats
                            chat_count += 1
                            formatted_chats[f"chat_{chat_count}"] = formatted_chat

                # Handle composer data
                elif 'allComposers' in data:
                    for composer in data['allComposers']:
                        formatted_chat = self._format_composer_chat(composer, chat_count + 1)
                        if formatted_chat.strip():  # Only include non-empty chats
                            chat_count += 1
                            formatted_chats[f"chat_{chat_count}"] = formatted_chat

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

    def export(self, chat_data: list[str], output_dir: str, image_dir: str, tab_ids: list[int] | None = None) -> None:
        """Export the chat data by formatting and saving it.

        Args:
            chat_data (list[str]): List of JSON strings containing chat data.
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

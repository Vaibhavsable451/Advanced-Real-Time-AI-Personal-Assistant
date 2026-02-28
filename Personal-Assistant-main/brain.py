from dotenv import load_dotenv

import subprocess
import logging
import os
import sys
import asyncio
import re

from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions
from livekit.plugins import (
    google,
    noise_cancellation,
)
from jarvis_prompt import behavior_prompt as behavior_prompts, Reply_prompts

from jarvis_search import google_search, get_current_datetime
from memory_store import ConversationMemory

from jarvis_get_whether import get_weather
from Jarvis_window_CTRL import (
    open_common_app, open_file, run_application_or_media,
    shutdown_system, restart_system, sleep_system, lock_screen,
    capture_photo, send_whatsapp_message
)
from Jarvis_file_opner import Play_file
from keyboard_mouse_CTRL import move_cursor_tool, mouse_click_tool, scroll_cursor_tool, type_text_tool, press_key_tool, swipe_gesture_tool, press_hotkey_tool, control_volume_tool

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Shared memory instance
_memory = ConversationMemory(user_id="jarvis_user")

from livekit.agents import function_tool

@function_tool
async def load_memory() -> str:
    """Load all past memory/conversations for the user."""
    entries = _memory.load_memory()
    return str(entries) if entries else "अभी तक कोई बातचीत याद नहीं है"

@function_tool
async def get_recent_conversations(limit: int = 5) -> str:
    """Get recent conversation context."""
    msgs = _memory.get_recent_context(max_messages=limit)
    if not msgs:
        return "अभी तक कोई बातचीत याद नहीं है"
    return "\n".join([f"{m.get('role','')}: {m.get('content','')}" for m in msgs])

@function_tool
async def add_memory_entry(content: str) -> str:
    """Save a note or memory entry."""
    _memory.save_conversation({"messages": [{"role": "note", "content": content}]})
    return "Memory saved!"

@function_tool
async def save_memory(key: str, value: str) -> str:
    """Save a key-value memory entry."""
    _memory.save_conversation({"messages": [{"role": "memory", "content": f"{key}: {value}"}]})
    return f"Saved: {key} = {value}"

# Memory interceptor flag - set to True to enable client-side memory injection
ENABLE_MEMORY_INTERCEPTOR = True


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=behavior_prompts,
                         tools=[
                            google_search,
                            get_current_datetime,
                            get_weather,
                            open_common_app,
                            open_file,
                            run_application_or_media,
                            shutdown_system,
                            restart_system,
                            sleep_system,
                            lock_screen,
                            capture_photo,
                            send_whatsapp_message,
                            load_memory, save_memory,
                            get_recent_conversations,
                            add_memory_entry,
                            Play_file,
                            move_cursor_tool,
                            mouse_click_tool,
                            scroll_cursor_tool,
                            type_text_tool,
                            press_key_tool,
                            press_hotkey_tool,
                            control_volume_tool,
                            swipe_gesture_tool
                         ]
                         )


async def entrypoint(ctx: agents.JobContext):
    """Entry point for LiveKit agent session with improved error handling"""
    max_retries = 5  # Increased from 3
    retry_count = 0
    base_wait_time = 3  # Increased from 2
    
    while retry_count < max_retries:
        try:
            print(f"\n🚀 Starting agent session (attempt {retry_count + 1}/{max_retries})...")
            
            session = AgentSession(
                llm=google.beta.realtime.RealtimeModel(
                    model="gemini-2.5-flash-native-audio-latest",
                    voice="Charon"
                )
            )
            
            await session.start(
                room=ctx.room,
                agent=Assistant(),
                room_input_options=RoomInputOptions(
                    noise_cancellation=noise_cancellation.BVC(),
                    video_enabled=True 
                ),
            )

            await ctx.connect()
            print("✅ Connected to room, waiting for audio input...")

            # Generate reply with timeout handling
            try:
                # Try to inject memory context into the reply instructions
                instructions = Reply_prompts
                
                if ENABLE_MEMORY_INTERCEPTOR:
                    try:
                        print("🧠 Fetching memory context...")
                        # Fetch recent conversations to inject context
                        memory_context = await get_recent_conversations(limit=5)  # Reduced from 10
                        
                        # Only inject if there's actual memory, keep it brief
                        if "अभी तक कोई बातचीत याद नहीं है" not in memory_context:
                            instructions = f"""{Reply_prompts}

[RECENT CONTEXT]
{memory_context}
[/CONTEXT]"""
                            print("✅ Memory context injected")
                        else:
                            instructions = Reply_prompts
                            print("ℹ️ No previous conversations to inject")
                    except Exception as e:
                        print(f"⚠️ Memory injection skipped: {e}")
                        instructions = Reply_prompts
                
                print("📡 Sending instructions to LLM (this may take a moment)...")
                await session.generate_reply(
                    instructions=instructions
                )
                print("✅ Session completed successfully")
                break  # Success - exit retry loop
                
            except Exception as e:
                error_msg = str(e).lower()
                print(f"⚠️ Reply generation error (attempt {retry_count + 1}/{max_retries}): {e}")
                
                # Check if it's a timeout/connection error worth retrying
                if any(keyword in error_msg for keyword in ["timed out", "timeout", "connection", "websocket", "closed"]):
                    if retry_count < max_retries - 1:
                        retry_count += 1
                        wait_time = base_wait_time * retry_count  # Exponential backoff
                        print(f"🔄 Connection issue detected. Retrying in {wait_time}s... ({retry_count}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        print("❌ Max retries exceeded after multiple timeouts")
                        raise
                else:
                    # Not a timeout - propagate error immediately
                    raise
            
        except KeyboardInterrupt:
            print("\n⛔ Agent stopped by user")
            break
        except Exception as e:
            print(f"❌ Session error (attempt {retry_count + 1}/{max_retries}): {e}")
            retry_count += 1
            
            if retry_count < max_retries:
                wait_time = base_wait_time * retry_count  # Exponential backoff
                print(f"⏳ Waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)
            else:
                print("❌ Max retries exceeded. Shutting down.")
                raise


if __name__ == "__main__":
    # Try to start the GUI alongside the agent (runs in a separate process)
    try:
        gui_path = os.path.join(os.path.dirname(__file__), "jarvis_ui.py")
        if os.path.exists(gui_path):
            # Start GUI as a detached subprocess so the agent can continue
            subprocess.Popen([sys.executable, gui_path], stdout=None, stderr=None, stdin=None, close_fds=True)
        else:
            print("jarvis_ui.py not found; GUI will not be started.")
    except Exception as e:
        print("Failed to start GUI subprocess:", e)

    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))

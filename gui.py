import sys
import os
import subprocess
import tkinter as tk
from tkinter import messagebox, filedialog
import requests
import websocket
import threading
import unicodedata
import atexit
import queue
import time


# Determine the correct path to 'server.js' when the app is packaged
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# Function to start the Node server executable (server.exe)
def start_server():
    try:
        # Determine the correct path for the executable
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
            server_path = os.path.join(base_path, 'server.exe')
            proc = subprocess.Popen([server_path, port_entry.get().strip()])
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
            # Development: run server.js with Node
            server_path = os.path.join(base_path, 'server.js')
            proc = subprocess.Popen(["node", server_path, port_entry.get().strip()])

        print("Waiting for server to start...")
        time.sleep(5)

        if proc.poll() is not None:
            print("Server failed to start.")
            return None

        print(f"Server started successfully on port {port_entry.get().strip()}.")
        return proc

    except Exception as e:
        print("Failed to start server:", e)
        return None

# Function to start the listener in a separate thread
def start_listener():
    try:
        import listener
    except ImportError as e:
        print("Listener module import failed:", e)
        return

    port = port_entry.get().strip()
    if not port.isdigit():
        print("Invalid port specified for listener.")
        return

    listener_thread = threading.Thread(target=listener.run_listener, args=(int(port),), daemon=True)
    listener_thread.start()
    print(f"Listener started in background on port {port}.")


# Function to start the backend server and listener after GUI initialization
def start_backend():
    global server_process
    server_process = start_server()  # Start the server
    start_listener()  # Start the listener in the background
    atexit.register(lambda: server_process.terminate() if server_process else None)

# GUI setup
root = tk.Tk()
root.title("Username Compiler")

# ---- Top: Port Entry ----
port_frame = tk.Frame(root)
port_frame.pack(pady=5)

tk.Label(port_frame, text="Port:").pack(side=tk.LEFT)
port_entry = tk.Entry(port_frame, width=6)
port_entry.insert(0, "8080")  # Default port
port_entry.pack(side=tk.LEFT, padx=5)

tk.Button(port_frame, text="Submit", command=lambda: submit_port()).pack(side=tk.LEFT, padx=5)
port_entry.bind("<Return>", lambda event: submit_port())

# Start the backend after the GUI is initialized
def delayed_backend_start():
    start_backend()
    # Start WebSocket connection after backend and GUI are ready
    root.after(100, lambda: threading.Thread(target=listen_ws, daemon=True).start())

root.after(100, delayed_backend_start)

divider0 = tk.Frame(root, bg="black", height=2)
divider0.pack(fill=tk.X, pady=10)

def submit_port():
    port = port_entry.get().strip()
    if not port:
        messagebox.showerror("Error", "Port is required.")
        return
    try:
        update_status(f"Starting server on port {port}", "orange")
        start_backend()  # Start the server
        # Attempt to start the WebSocket connection
        retry_button.config(state=tk.DISABLED)  # Disable retry button until the WebSocket is connected
        threading.Timer(5, lambda: threading.Thread(target=listen_ws, daemon=True).start()).start()
    except Exception:
        update_status("❌ Could not start server", "red")


# Globals
ws = None
viewer_set = set()
nickname_map = {}
current_username = ""
node_process = None
server_process = None  # Ensure this is defined globally


# ---- Streamer Username and Keyword (Side-by-Side) ----
form_frame = tk.Frame(root)
form_frame.pack()

# Streamer Username
username_column = tk.Frame(form_frame)
username_column.pack(side=tk.LEFT, padx=10)

tk.Label(username_column, text="Streamer Username:").pack()
username_entry = tk.Entry(username_column, width=25)
username_entry.pack()

status_queue = queue.Queue()

# Define helper functions first
def update_status(message, color):
    status_label.config(text=message, fg=color)

def check_status_queue():
    try:
        while True:
            status_message = status_queue.get_nowait()  # Non-blocking get
            if status_message == "WebSocket connected":
                update_status("✅ WebSocket connected", "green")
    except queue.Empty:
        pass

    # Continue checking the queue every 100ms
    root.after(100, check_status_queue)


def update_username_status(text, color="red"):
    username_status_label.config(text=text, fg=color)

def update_keyword_status(text, color="red"):
    keyword_status_label.config(text=text, fg=color)

def clear_username():
    global current_username
    username_entry.delete(0, tk.END)
    update_username_status("", "red")
    current_username = ""
    try:
        port = port_entry.get()
        requests.post(f"http://localhost:{port}/disconnect")
    except Exception:
        pass

def clear_keyword():
    global current_keyword
    keyword_entry.delete(0, tk.END)
    update_keyword_status("", "red")
    current_keyword = ""
    viewer_text.delete("1.0", tk.END)
    viewer_set.clear()
    nickname_map.clear()
    try:
        port = port_entry.get()
        requests.post(f"http://localhost:{port}/clearKeyword")
    except Exception:
        pass

# Then create the buttons
username_frame = tk.Frame(username_column)
username_frame.pack(pady=(5, 10))
tk.Button(username_frame, text="Submit", command=lambda: submit_username()).pack(side=tk.LEFT, padx=5)
tk.Button(username_frame, text="Clear", command=clear_username).pack(side=tk.LEFT, padx=5)
username_entry.bind("<Return>", lambda event: submit_username())

# Username status label
username_status_label = tk.Label(username_column, text="", anchor="w", fg="red")
username_status_label.pack()

# Keyword
keyword_column = tk.Frame(form_frame)
keyword_column.pack(side=tk.LEFT, padx=10)

tk.Label(keyword_column, text="Keyword (case-insensitive):").pack()
keyword_entry = tk.Entry(keyword_column, width=25)
keyword_entry.pack()

keyword_frame = tk.Frame(keyword_column)
keyword_frame.pack(pady=(5, 10))
tk.Button(keyword_frame, text="Submit", command=lambda: submit_keyword()).pack(side=tk.LEFT, padx=5)
tk.Button(keyword_frame, text="Clear", command=lambda: clear_keyword()).pack(side=tk.LEFT, padx=5)
keyword_entry.bind("<Return>", lambda event: submit_keyword())

# Keyword status label
keyword_status_label = tk.Label(keyword_column, text="", anchor="w", fg="red")
keyword_status_label.pack()

# ---- Divider ----
divider1 = tk.Frame(root, bg="black", height=2)
divider1.pack(fill=tk.X, pady=10)

# ---- Status Label ----
status_label = tk.Label(root, text="\ud83d\udd34 Not connected", anchor="center", justify="center", fg="red")
status_label.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(10, 5))

def submit_username():
    global current_username
    username = username_entry.get().strip()
    if not username:
        update_username_status("Streamer username is required.", "red")
        return
    current_username = username
    try:
        port = port_entry.get()
        res = requests.post(f"http://localhost:{port}/start", json={"username": username})
        try:
            data = res.json()
        except Exception as parse_err:
            print("❌ JSON parse error:", parse_err)
            data = {}

        print("📦 Response status:", res.status_code)
        print("📦 Response JSON:", data)


        if res.status_code == 200 and data.get("success") == True:
            update_username_status(f"Streamer: @{username}", "green")
        else:
            error_msg = data.get("error", "Connection failed")
            print(f"❌ Server error: {res.status_code} - {error_msg}")
            update_username_status(f"❌ {error_msg}", "red")

    except Exception as e:
        update_username_status(f"❌ Could not connect to server: {e}", "red")


def submit_keyword():
    keyword = keyword_entry.get().strip()  # Remove strip().lower() since server handles case
    if not keyword:
        update_keyword_status("Keyword is required.", "red")
        return
    try:
        port = port_entry.get()
        res = requests.post(f"http://localhost:{port}/keyword", json={"keyword": keyword})
        if res.ok:
            update_keyword_status(f"Keyword set: {keyword}", "green")
            clear_text()
        else:
            update_keyword_status("❌ Failed to set keyword", "red")
    except Exception:
        update_keyword_status("❌ Could not reach server", "red")

# ---- Display Options ----
tk.Label(root, text="Display Format:").pack()
name_button_frame = tk.Frame(root)
name_button_frame.pack(pady=5)

def copy_to_clipboard(text):
    root.clipboard_clear()
    root.clipboard_append(text)

def sanitize_name(name):
    cleaned = ''.join(
        c if c.isspace() or unicodedata.category(c).startswith('L') else ' '
        for c in unicodedata.normalize('NFKD', name)
    )
    return ' '.join(cleaned.split()).strip()

def show_unsanitized_names():
    names = list(nickname_map.values())
    result = ", ".join(names)
    viewer_text.delete("1.0", tk.END)
    viewer_text.insert(tk.END, result)
    copy_to_clipboard(result)

def show_sanitized_name():
    sanitized = [
        sanitize_name(nickname).capitalize()
        for nickname in nickname_map.values()
    ]
    result = ", ".join(dict.fromkeys(sanitized))  # Preserve order & remove duplicates
    viewer_text.delete("1.0", tk.END)
    viewer_text.insert(tk.END, result)
    copy_to_clipboard(result)

def show_first_word():
    first_words = []
    seen = set()
    for nickname in nickname_map.values():
        cleaned = sanitize_name(nickname)
        words = cleaned.split()
        if words:
            word = words[0].capitalize()
            if word not in seen:
                seen.add(word)
                first_words.append(word)
    result = ", ".join(first_words)
    viewer_text.delete("1.0", tk.END)
    viewer_text.insert(tk.END, result)
    copy_to_clipboard(result)


tk.Button(name_button_frame, text="Unsanitized Names", command=show_unsanitized_names).pack(side=tk.LEFT, padx=5)
tk.Button(name_button_frame, text="Sanitized Names", command=show_sanitized_name).pack(side=tk.LEFT, padx=5)
tk.Button(name_button_frame, text="First Word Only", command=show_first_word).pack(side=tk.LEFT, padx=5)

# ---- Divider ----
divider2 = tk.Frame(root, bg="black", height=2)
divider2.pack(fill=tk.X, pady=10)

# ---- Viewer Names Output ----
tk.Label(root, text="Viewer Names:").pack()
viewer_text = tk.Text(root, height=10, width=50)
viewer_text.pack()

# ---- Bottom Controls ----
bottom_frame = tk.Frame(root)
bottom_frame.pack(pady=10)

def clear_text():
    viewer_set.clear()
    nickname_map.clear()
    viewer_text.delete("1.0", tk.END)

# Update the clear_all function
def clear_all():
    clear_username()
    clear_keyword()
    # WebSocket connection remains intact
    update_status("✅ WebSocket connected", "green")

def save_to_file():
    content = viewer_text.get("1.0", tk.END).strip()
    if not content:
        return
    file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
    if file_path:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

def copy_list():
    content = viewer_text.get("1.0", tk.END).strip()
    if content:
        copy_to_clipboard(content)

tk.Button(bottom_frame, text="Copy List", command=copy_list).pack(side=tk.LEFT, padx=5)
tk.Button(bottom_frame, text="Save List", command=save_to_file).pack(side=tk.LEFT, padx=5)
tk.Button(bottom_frame, text="Clear All", command=clear_all).pack(side=tk.LEFT, padx=5)

# ---- Retry WebSocket Button ----
retry_button = tk.Button(bottom_frame, text="Reconnect", command=lambda: retry_ws(), state=tk.DISABLED)
retry_button.pack(side=tk.LEFT, padx=5)

# WebSocket Logic
def on_message(ws, message):
    if message == 'clearViewers':
        root.after(0, lambda: viewer_text.delete("1.0", tk.END))
        viewer_set.clear()
        nickname_map.clear()
        return

    if isinstance(message, str):
        nickname = message.strip()
        if nickname and nickname not in viewer_set:
            viewer_set.add(nickname)
            nickname_map[nickname] = nickname
            root.after(0, lambda: viewer_text.insert(tk.END, nickname + ", "))
            root.after(0, lambda: viewer_text.see(tk.END))

# Flag to track WebSocket connection status
ws_connected = False

# Update on_open function to force immediate UI update
def on_open(ws):
    global ws_connected
    if not ws_connected:  # Update only if not already connected
        ws_connected = True
        print("✅ WebSocket connection opened")
        root.after(0, update_status, "✅ WebSocket connected", "green")


def on_error(ws, error):
    print(f"❌ WebSocket error: {error}")
    root.after(0, update_status, f"❌ WebSocket error: {error}", "red")

def on_close(ws, close_status_code, close_msg):
    print("🔴 WebSocket connection closed")
    root.after(0, update_status, "🔴 WebSocket disconnected", "red")


def listen_ws():
    global ws_connected
    try:
        # Show "Attempting to connect" status immediately
        root.after(0, update_status, "⏳ Attempting to connect...", "orange")

        ws_app = websocket.WebSocketApp(
            f"ws://localhost:{port_entry.get()}",
            on_message=on_message,
            on_open=on_open,
            on_error=on_error,
            on_close=on_close
        )
        ws = ws_app
        ws_app.run_forever(ping_interval=30, ping_timeout=10)

    except Exception as e:
        print(f"WebSocket connection error: {e}")
        def fail():
            update_status(f"❌ WebSocket connection failed: {e}", "red")
            def fail():
                update_status(f"❌ WebSocket connection failed: {e}", "red")
                retry_button.config(state=tk.NORMAL)
                root.after(0, fail)

        root.after(0, fail)

def retry_ws():
    retry_button.config(state=tk.DISABLED)
    update_status("⏳ Retrying WebSocket connection...", "blue")
    threading.Thread(target=listen_ws, daemon=True).start()

# Update the on_close_window function
def on_close_window():
    global node_process
    try:
        # First disconnect from TikTok stream
        port = port_entry.get()
        requests.post(f"http://localhost:{port}/disconnect")
        
        # Then close WebSocket
        if ws:
            ws.close()
            
        # Finally terminate Node process
        if node_process:
            node_process.terminate()
            node_process.wait(timeout=5)  # Wait up to 5 seconds for process to terminate
    except Exception as e:
        print(f"Error during cleanup: {e}")

if __name__ == "__main__":
    root.mainloop()
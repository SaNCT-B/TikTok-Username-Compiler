import websocket
import json
import threading

# Global reference to the GUI label
status_label = None

def update_status(text):
    """Update the WebSocket status label in the GUI."""
    if status_label:
        status_label.config(text=text)
        status_label.update_idletasks()  # Force immediate refresh

def on_message(ws, message):
    try:
        data = json.loads(message)
        if data.get('type') == 'chat':
            viewer_name = data.get('viewerName', 'Unknown')
            chat_message = data.get('message', '')
            print(f"{viewer_name} said: {chat_message}")
    except json.JSONDecodeError:
        if message == "clearViewers":
            print("🔄 Received clearViewers command.")
        else:
            print("Received non-JSON message:", message)

def on_error(ws, error):
    print(f"WebSocket Error: {error}")
    update_status("WebSocket Error")

def on_close(ws, close_status_code, close_msg):
    print(f"WebSocket Closed: Code={close_status_code}, Message={close_msg}")
    update_status("Not connected")

def on_open(ws):
    print("WebSocket connection opened.")
    update_status("Connected")  # Update the label when connected

def run_listener(port=8080):
    ws_url = f"ws://localhost:{port}"
    ws_app = websocket.WebSocketApp(
        ws_url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws_app.on_open = on_open
    ws_app.run_forever()

def start_listener(port=8080, label=None):
    """Start the WebSocket listener in a background thread and update the GUI label."""
    global status_label
    status_label = label  # Assign the label reference

    listener_thread = threading.Thread(target=run_listener, args=(port,), daemon=True)
    listener_thread.start()
    print(f"Listener started in background on port {port}.")
    update_status("Connecting...")  # Show "Connecting..." while waiting for WebSocket

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        run_listener(int(sys.argv[1]))
    else:
        run_listener(8080)
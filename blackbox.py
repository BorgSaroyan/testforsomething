import time
import requests
from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

def send_request(messages, max_tokens=4096, temperature=None, top_p=None):
    api_url = "https://www.blackbox.ai/api/chat"
    
    # Generate a unique ID
    timestamp = hex(int(time.time() * 1000))[2:9]
    
    # Prepare headers
    headers = {
        "authority": "www.blackbox.ai",
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "origin": "https://www.blackbox.ai",
        "referer": "https://www.blackbox.ai/",
        "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Mobile Safari/537.36"
    }
    
    # Prepare payload
    payload = {
        "messages": messages,
        "agentMode": {},
        "id": timestamp,
        "previewToken": None,
        "userId": None,
        "codeModelMode": False,
        "trendingAgentMode": {},
        "isMicMode": False,
        "userSystemPrompt": None,
        "maxTokens": max_tokens,
        "playgroundTopP": top_p,
        "playgroundTemperature": temperature,
        "isChromeExt": False,
        "githubToken": "",
        "clickedAnswer2": False,
        "clickedAnswer3": False,
        "clickedForceWebSearch": False,
        "visitFromDelta": False,
        "isMemoryEnabled": False,
        "mobileClient": False,
        "userSelectedModel": "claude-3-7-sonnet",
        "validated": "00f37b34-a166-4efb-bce5-1312d87f2f94",
        "imageGenerationMode": False,
        "webSearchModePrompt": False,
        "deepSearchMode": False,
        "domains": None,
        "vscodeClient": False,
        "codeInterpreterMode": False
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=payload)
        return response if response.ok else None
    except Exception as e:
        print(f"Error making request: {e}")
        return None

@app.route("/v1/messages", methods=["POST"])
@app.route("/messages", methods=["POST"])
def handle_messages():
    request_data = request.json
    formatted_messages = []
    
    # Handle system message if present
    if request_data.get("system"):
        system_content = request_data["system"][0].get("text", "")
        formatted_messages.append({"role": "system", "content": system_content})
    
    # Process user and assistant messages
    for message in request_data.get("messages", []):
        role = message.get("role")
        content_items = message.get("content", [])
        for content_item in content_items:
            text = content_item.get("text", "")
            msg_id = hex(int(time.time() * 1000))[2:9]
            formatted_messages.append({"role": role, "content": text, "id": msg_id})
    
    max_tokens = request_data.get("max_tokens", 4096)
    temperature = request_data.get("temperature")
    top_p = request_data.get("top_p")
    response = send_request(formatted_messages, max_tokens=max_tokens, temperature=temperature, top_p=top_p)
    
    if response and response.ok:
        return {
            "type": "message",
            "content": [{"type": "text", "text": response.text}]
        }
    else:
        status = response.status_code if response else "Unknown"
        return jsonify({"error": f"Request failed with status {status}"}), 500

@app.route("/v1/chat/completions", methods=["POST"])
@app.route("/chat/completions", methods=["POST"])
def handle_openai_completions():
    request_data = request.json
    formatted_messages = []
    
    # Handle system message if present
    if request_data.get("messages") and request_data["messages"][0].get("role") == "system":
        system_message = request_data["messages"].pop(0)
        formatted_messages.append({"role": "system", "content": system_message.get("content", "")})
    
    # Process user messages
    for message in request_data.get("messages", []):
        formatted_messages.append({"role": message.get("role"), "content": message.get("content")})
    
    max_tokens = request_data.get("max_tokens", 4096)
    temperature = request_data.get("temperature")
    top_p = request_data.get("top_p")
    response = send_request(formatted_messages, max_tokens=max_tokens, temperature=temperature, top_p=top_p)
    
    if response and response.ok:
        return jsonify({
            "id": f"chatcmpl-{time.time()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "blackbox-claude-3-7-sonnet",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": response.text},
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(" ".join([m.get("content", "") for m in formatted_messages])),
                "completion_tokens": len(response.text),
                "total_tokens": len(" ".join([m.get("content", "") for m in formatted_messages])) + len(response.text)
            }
        })
    else:
        status = response.status_code if response else "Unknown"
        return jsonify({"error": {"message": f"Request failed with status {status}"}}), 500

@app.route("/v1/models", methods=["GET"])
@app.route("/models", methods=["GET"])
def list_models():
    return jsonify({
        "object": "list",
        "data": [{
            "id": "claude-3-7-sonnet",
            "object": "model",
            "created": int(time.time()),
            "owned_by": "blackbox-ai"
        }]
    })

@app.route("/", methods=["GET"])
def stats_page():
    return "Service is running at http://localhost:7860"

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=7860)
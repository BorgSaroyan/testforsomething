import json
import http.server
import urllib.request
import urllib.error
import os
import logging
import urllib.parse

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PORT = 9090
REVE_API_URL = "https://preview.reve.art/api/misc/chat"
MODEL_MAPPING = {
    "claude-3-7-sonnet-20250219": "llm_claude_sonnet_3_7",
    "claude-3-7-sonnet-latest": "llm_claude_sonnet_3_7",
    "claude-3-5-sonnet-20241022": "llm_claude_sonnet_3_5_v2",
    "claude-3-5-sonnet-latest": "llm_claude_sonnet_3_5_v2",
    "claude-3-5-sonnet-20240620": "llm_claude_sonnet_3_5",
    "claude-3-5-haiku-20241022": "llm_claude_haiku_3_5_v2",
    "claude-3-5-haiku-latest": "llm_claude_haiku_3_5_v2"
}

def convert_anthropic_to_reve_request(anthropic_req):
    model = anthropic_req.get("model", "claude-3-7-sonnet-latest")
    reve_model = MODEL_MAPPING.get(model, "llm_claude_sonnet_3_7")

    system_prompt = anthropic_req.get("system", "")
    
    if isinstance(system_prompt, list):
        system_text_chunks = []
        for item in system_prompt:
            if isinstance(item, dict) and item.get("type") == "text":
                system_text_chunks.append(item.get("text", ""))
            elif isinstance(item, str):
                system_text_chunks.append(item)
        system_prompt = "\n".join(system_text_chunks)
    
    max_tokens = anthropic_req.get("max_tokens", 8192)
    
    temperature = anthropic_req.get("temperature", 1.0)
    temperature_percent = int(temperature * 100)
    
    conversation = []
    for msg in anthropic_req.get("messages", []):
        role = msg.get("role", "user")
        
        content = msg.get("content", "")
        multi_content = []
        
        if isinstance(content, str):
            multi_content = [{"text": content}]
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, str):
                    multi_content.append({"text": item})
                elif isinstance(item, dict):
                    if item.get("type") == "text":
                        multi_content.append({"text": item.get("text", "")})
                    elif item.get("type") == "image":
                        # Doesn't work for some reason
                        # {"error_code":"UPSTREAM_ERROR","message":"Model inference failed","instance_id":"error-redacted"}
                        src = item["source"]
                        multi_content.append({
                            "image": {
                                "type": src["type"],
                                "media_type": src["type"],
                                "data": src["data"]
                            }
                        })
        
        conversation.append({
            "role": role,
            "multi_content": multi_content
        })
    
    reve_req = {
        "model": reve_model,
        "max_length": max_tokens,
        "system_prompt": system_prompt,
        "temperature_percent": temperature_percent,
        "conversation": conversation
    }
    
    return reve_req

def convert_reve_to_anthropic_response(reve_resp, reve_model):
    content = reve_resp.get("response", "")
    
    anthropic_model = next((anthr_model for anthr_model, rev_model in MODEL_MAPPING.items() 
                         if rev_model == reve_model), "claude-3-7-sonnet-20250219")
    
    anthropic_resp = {
        "id": "msg_" + os.urandom(8).hex(),
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": content
            }
        ],
        "model": anthropic_model,
        "stop_reason": reve_resp.get("stop_reason", "end_turn"),
        "stop_sequence": None,
        "usage": {
            "input_tokens": reve_resp.get("prompt_tokens", 0),
            "output_tokens": reve_resp.get("completion_tokens", 0)
        }
    }
    
    return anthropic_resp

class AnthropicProxyHandler(http.server.BaseHTTPRequestHandler):
    def send_json_response(self, status_code, data):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
    
    def do_POST(self):
        if self.path != "/v1/messages":
            self.send_error(404, "Not found")
            return
            
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            anthropic_req = json.loads(self.rfile.read(content_length).decode('utf-8'))
            
            if anthropic_req.get("stream", False):
                self.send_json_response(400, {
                    "error": {
                        "type": "invalid_request_error",
                        "message": "Streaming is not supported by this proxy."
                    }
                })
                return
            
            reve_req = convert_anthropic_to_reve_request(anthropic_req)
            reve_model = reve_req['model']
            logger.info(f"Doing request with model {reve_model}")

            headers = {
                "Content-Type": "application/json; charset=utf-8"
            }
            
            try:
                req = urllib.request.Request(
                    REVE_API_URL,
                    data=json.dumps(reve_req).encode('utf-8'),
                    headers=headers,
                    method="POST"
                )
                
                with urllib.request.urlopen(req) as response:
                    reve_resp = json.loads(response.read().decode('utf-8'))
                    logger.info(f"Received Reve response.")
                    self.send_json_response(200, convert_reve_to_anthropic_response(reve_resp, reve_model))
                    
            except urllib.error.HTTPError as e:
                status_code = e.code
                error_text = e.read().decode('utf-8')
                logger.error(f"API error ({status_code}): {error_text}")
                self.send_response(status_code)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(error_text.encode('utf-8'))
                
            except Exception as e:
                logger.error(f"Error calling Reve API: {str(e)}")
                self.send_json_response(500, {"error": str(e)})
        
        except Exception as e:
            logger.error(f"Error processing request: {str(e)}")
            self.send_error(500, "Error processing request")

def main():
    handler = AnthropicProxyHandler
    with http.server.HTTPServer(("", PORT), handler) as httpd:
        logger.info(f"Proxy server running on port {PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Server stopped by keyboard interrupt")
            httpd.shutdown()
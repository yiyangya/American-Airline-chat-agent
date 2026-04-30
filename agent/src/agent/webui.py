#!/usr/bin/env python3
"""
Web UI for Agent

Simple Flask-based web interface for chatting with the agent.
Provides a chat interface with Server-Sent Events for streaming responses.
"""

import argparse
import json
from flask import Flask, request, jsonify, Response, render_template

from .agent import ToolCallingAgent
from .tool_manager import ToolManager
from .prompt_injection_detector import PromptInjectionError

# Initialize Flask app
app = Flask(__name__)
# Auto-reload Jinja templates when webui.html changes (no server restart needed)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.jinja_env.auto_reload = True

# Global state
tool_manager = None
agent = None
mcp_server_status = []


def create_agent():
    """Create a new agent instance with the current tool manager."""
    global agent
    agent = ToolCallingAgent(tool_manager)


@app.route('/')
@app.route('/index.html')
def index():
    """Serve the HTML interface."""
    return render_template('webui.html')


@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat messages with Server-Sent Events streaming."""
    import queue
    import threading

    data = request.json
    message = data.get('message', '')

    if not message:
        return jsonify({'error': 'No message provided'}), 400

    # Queue to communicate between threads
    event_queue = queue.Queue()

    def run_agent():
        """Run agent in separate thread and put results in queue."""
        import sys
        import io

        # Capture stdout to intercept rate limit messages
        class OutputCapture(io.StringIO):
            def write(self, text):
                if '⏱️' in text:
                    # Send waiting event immediately
                    event_queue.put(('waiting', text.strip()))
                return super().write(text)

        old_stdout = sys.stdout
        sys.stdout = OutputCapture()

        try:
            response = agent.execute(message)
            event_queue.put(('response', response))
        except PromptInjectionError as e:
            event_queue.put(('error', f"⚠️ Security Warning: {str(e)}"))
        except Exception as error:
            event_queue.put(('error', str(error)))
        finally:
            sys.stdout = old_stdout
            event_queue.put(('done', None))

    def generate():
        """Generator for Server-Sent Events."""
        # Start agent in background thread
        thread = threading.Thread(target=run_agent, daemon=True)
        thread.start()

        # Stream events as they come from the queue
        while True:
            event_type, data = event_queue.get()

            if event_type == 'waiting':
                yield f"event: waiting\ndata: {json.dumps({'message': data})}\n\n"
            elif event_type == 'response':
                yield f"event: response\ndata: {json.dumps({'message': data})}\n\n"
            elif event_type == 'error':
                yield f"event: error\ndata: {json.dumps({'message': data})}\n\n"
            elif event_type == 'done':
                yield f"event: done\ndata: {{}}\n\n"
                break

    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/mcp-servers', methods=['GET'])
def get_mcp_servers():
    """Get MCP server status."""
    return jsonify(mcp_server_status)


@app.route('/api/reset', methods=['POST'])
def reset():
    """Reset the agent conversation."""
    create_agent()
    return jsonify({'success': True})


def main():
    """Main entry point for the web UI."""
    parser = argparse.ArgumentParser(
        description="Run agent web UI with MCP servers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  agent-webui "http://localhost:3000/mcp"
        """
    )

    parser.add_argument(
        'mcp_servers',
        nargs='*',
        help='MCP server URLs or commands'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='Port to run the web server on (default: 8000)'
    )

    args = parser.parse_args()

    # Initialize global tool manager
    global tool_manager, mcp_server_status
    tool_manager = ToolManager.from_servers(args.mcp_servers)

    # Get server status
    statuses = tool_manager.get_server_status()
    mcp_server_status = [
        {
            'config': status.config,
            'transport': status.transport,
            'status': status.status,
            'error': status.error
        }
        for status in statuses
    ]

    # Create initial agent
    create_agent()

    # Start server
    print(f"\n🌐 Server running at http://localhost:{args.port}\n")
    app.run(host='0.0.0.0', port=args.port, debug=False)


if __name__ == '__main__':
    main()

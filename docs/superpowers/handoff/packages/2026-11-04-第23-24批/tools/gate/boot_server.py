"""Start the merged tree's server with the model pointed at 127.0.0.1:9 (never 11434): boot_server.py <tree> <port>."""
import sys

sys.path.insert(0, sys.argv[1])
import server  # noqa: E402

server.CONTENT.config.ollama_url = "http://127.0.0.1:9"
server.main(["--port", sys.argv[2]])

import os
import threading
from flask import Flask, jsonify
import logging

from main import run_job

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def background_task():
    try:
        logging.info("Starting background run_job()...")
        run_job()
        logging.info("Finished background run_job().")
    except Exception as e:
        logging.error(f"Error in background task: {e}")

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    logging.info("Received webhook trigger.")
    
    # Spawn a background thread to run the main job
    # This allows the Flask app to immediately return a 200 OK response
    # to Apps Script, avoiding the serverless timeout.
    thread = threading.Thread(target=background_task)
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "success", "message": "Background job started."}), 200

@app.route('/', methods=['GET'])
def health():
    return jsonify({"status": "ok", "message": "Marketing Agent Webhook Server is running!"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

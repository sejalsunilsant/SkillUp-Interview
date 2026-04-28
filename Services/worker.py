import os
import sys
import redis
from rq import Worker, Queue, Connection

# Add project root to path
sys.path.append(os.getcwd())

# Pre-import to ensure classes are loaded
from Services.Genrator import GroqChatService

listen = ['groq_heavy_tasks']
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')

conn = redis.from_url(redis_url)

if __name__ == '__main__':
    with Connection(conn):
        print(f"--- Starting Redis Worker for queue: {listen} ---")
        worker = Worker(list(map(Queue, listen)))
        worker.work()

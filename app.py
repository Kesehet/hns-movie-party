from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit
import os
from flask import send_from_directory



app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global video timestamps
# Global video timestamps + play state
timestamps = {}  # { 'video.mp4': {'time': float, 'isPlaying': bool} }
current_video = {'name': None}


VIDEO_DIR = 'videos'  # Folder containing videos

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/videos/<path:filename>')
def serve_video(filename):
    return send_from_directory(VIDEO_DIR, filename)


@app.route('/videos')
def list_videos():
    files = [f for f in os.listdir(VIDEO_DIR) if f.endswith('.mp4')]
    for f in files:
        if f not in timestamps:
            timestamps[f] = {'time': 0, 'isPlaying': False}
    return jsonify(files)


@socketio.on('connect')
def on_connect():
    print('Client connected')
    emit('sync', {
        'current_video': current_video['name'],
        'timestamps': timestamps
    })

@socketio.on('host_update')
def on_host_update(data):
    video = data.get('video')
    timestamp = data.get('timestamp')
    isPlaying = data.get('isPlaying', False)
    if video in timestamps:
        timestamps[video] = {'time': timestamp, 'isPlaying': isPlaying}
        current_video['name'] = video
        emit('sync', {
            'current_video': video,
            'timestamps': timestamps
        }, broadcast=True)


if __name__ == '__main__':
    if not os.path.exists(VIDEO_DIR):
        os.makedirs(VIDEO_DIR)
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)

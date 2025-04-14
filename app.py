from flask import Flask, render_template, jsonify, send_from_directory, request, Response, abort
from flask_socketio import SocketIO, emit
import os
import datetime
import subprocess
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global video timestamps + play state
timestamps = {}  # { 'video.m3u8': {'time': float, 'isPlaying': bool} }
current_video = {'name': None}

VIDEO_DIR = 'videos'  # Folder containing HLS videos (m3u8 + ts)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/videos/<path:filename>')
def serve_video(filename):
    file_path = os.path.join(VIDEO_DIR, filename)

    if not os.path.isfile(file_path):
        abort(404)

    # Dynamically set MIME type
    if filename.endswith('.m3u8'):
        content_type = 'application/vnd.apple.mpegurl'
    elif filename.endswith('.ts'):
        content_type = 'video/MP2T'
    else:
        content_type = 'application/octet-stream'  # fallback

    with open(file_path, 'rb') as f:
        data = f.read()

    response = Response(data,
                        200,
                        mimetype=content_type,
                        direct_passthrough=True)
    file_size = os.path.getsize(file_path)
    response.headers.add('Content-Length', str(file_size))

    # Caching Headers
    expires = datetime.datetime.utcnow() + datetime.timedelta(days=365)
    response.headers['Cache-Control'] = 'public, max-age=31536000'
    response.headers['Expires'] = expires.strftime("%a, %d %b %Y %H:%M:%S GMT")

    return response


def convert_mp4_to_hls(mp4_path, output_dir):
    basename = os.path.splitext(os.path.basename(mp4_path))[0]
    output_m3u8 = os.path.join(output_dir, f"{basename}.m3u8")
    output_ts_pattern = os.path.join(output_dir, f"{basename}_%03d.ts")

    # Skip if already exists
    if os.path.exists(output_m3u8):
        return

    # Corrected FFmpeg command
    cmd = [
        'ffmpeg',
        '-i', mp4_path,
        '-c:v', 'copy',    # Correct codec syntax
        '-c:a', 'copy',    # Copy audio too
        '-start_number', '0',
        '-hls_time', '10',
        '-hls_list_size', '0',
        '-hls_segment_filename', output_ts_pattern,
        '-f', 'hls',
        output_m3u8
    ]

    try:
        subprocess.run(cmd, check=True)
        print(f"Converted {mp4_path} to HLS successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error converting {mp4_path} to HLS: {e.stderr}")


@app.route('/videos')
def list_videos():
    # Check if ffmpeg is available
    try:
        subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        ffmpeg_available = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        ffmpeg_available = False

    # Convert .mp4 to HLS if needed
    if ffmpeg_available:
        mp4_files = [f for f in os.listdir(VIDEO_DIR) if f.endswith('.mp4')]
        for mp4 in mp4_files:
            mp4_path = os.path.join(VIDEO_DIR, mp4)
            convert_mp4_to_hls(mp4_path, VIDEO_DIR)

    # List .m3u8 files
    files = [f for f in os.listdir(VIDEO_DIR) if f.endswith('.m3u8')]
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






ALLOWED_EXTENSIONS = {'ts', 'm3u8'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['GET', 'POST'])
def upload_files():
    if request.method == 'POST':
        if 'files[]' not in request.files:
            return "No files part", 400

        files = request.files.getlist('files[]')
        if not files:
            return "No selected files", 400

        saved_files = []
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                save_path = os.path.join(VIDEO_DIR, filename)
                file.save(save_path)
                saved_files.append(filename)

        return f"Uploaded: {', '.join(saved_files)}", 200

    # GET method - render upload form
    return render_template('upload.html')

if __name__ == '__main__':
    if not os.path.exists(VIDEO_DIR):
        os.makedirs(VIDEO_DIR)
    socketio.run(app, host='0.0.0.0', port=5000)

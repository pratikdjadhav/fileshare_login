from flask import (
    Flask, request, render_template, send_file, redirect,
    url_for, abort, Response, session, flash
)
from functools import wraps
from werkzeug.utils import secure_filename
import os
import time
import socket
import mimetypes
import shutil


app = Flask(__name__)
app.secret_key = 'pk'  # Replace with a strong random string

# Set this to your root directory
ROOT_DIR = "D:"

# Hardcoded login credentials
USERNAME = "pratik"
PASSWORD = "pk"

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def format_file_info(full_path):
    is_dir = os.path.isdir(full_path)
    size = os.path.getsize(full_path) if not is_dir else None
    mtime = time.strftime('%Y-%m-%d %H:%M', time.localtime(os.path.getmtime(full_path)))
    return {
        'name': os.path.basename(full_path),
        'path': os.path.relpath(full_path, ROOT_DIR).replace('\\', '/'),
        'is_dir': is_dir,
        'size': f"{size / 1024:.1f} KB" if size else "—",
        'mtime': mtime
    }

def get_all_files_recursive(root_dir, search_query=None):
    files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for name in dirnames + filenames:
            if search_query and search_query.lower() not in name.lower():
                continue
            full_path = os.path.join(dirpath, name)
            files.append(format_file_info(full_path))
    return files

@app.route('/', defaults={'req_path': ''})
@app.route('/<path:req_path>')
@login_required
def browse(req_path):
    abs_path = os.path.join(ROOT_DIR, req_path)
    search_query = request.args.get('q', '').strip().lower()
    sort_by = request.args.get('sort', '')
    

    if not os.path.exists(abs_path):
        return abort(404)

    if os.path.isfile(abs_path):
        return send_file(abs_path)

    try:
        if search_query:
            files = get_all_files_recursive(abs_path, search_query)
        else:
            files = []
            for f in os.listdir(abs_path):
                full_path = os.path.join(abs_path, f)
                files.append(format_file_info(full_path))
        # 🔽 Sort logic
        reverse = '_desc' in sort_by
        if sort_by.startswith('name'):
            files.sort(key=lambda x: x['name'].lower(), reverse=reverse)
        elif sort_by.startswith('size'):
            files.sort(key=lambda x: x['size'], reverse=reverse)
        elif sort_by.startswith('date'):
            files.sort(key=lambda x: x['mtime'], reverse=reverse)
        elif sort_by == 'type':
            files.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

    except PermissionError:
        return "Permission denied", 403

    return render_template("index.html", files=files, current_path=req_path, search_query=search_query)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == USERNAME and password == PASSWORD:
            session.permanent = False
            session['logged_in'] = True
            return redirect(url_for('browse'))
        else:
            flash('Invalid credentials')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))



@app.route('/upload/<path:req_path>', methods=['POST'])
def upload(req_path):
    abs_path = os.path.join(ROOT_DIR, req_path)

    if not os.path.exists(abs_path) or not os.path.isdir(abs_path):
        return "Invalid upload path", 400

    file = request.files.get('file')
    if not file:
        return "No file uploaded", 400

    filename = secure_filename(file.filename)
    file.save(os.path.join(abs_path, filename))

    return redirect(url_for('browse', req_path=req_path))


@app.route('/rename/<path:file_path>', methods=['GET', 'POST'])
def rename(file_path):
    abs_path = os.path.join(ROOT_DIR, file_path)
    if request.method == 'POST':
        new_name = request.form['new_name']
        new_path = os.path.join(os.path.dirname(abs_path), new_name)
        os.rename(abs_path, new_path)
        return redirect(url_for('browse', req_path=os.path.dirname(file_path)))
    return '''
        <form method="post">
            <input type="text" name="new_name" placeholder="New name" required>
            <button type="submit">Rename</button>
        </form>
    '''

@app.route('/delete/<path:file_path>')
def delete(file_path):
    abs_path = os.path.join(ROOT_DIR, file_path)
    if os.path.isfile(abs_path):
        os.remove(abs_path)
    elif os.path.isdir(abs_path):
        shutil.rmtree(abs_path)
    return redirect(url_for('browse', req_path=os.path.dirname(file_path)))

@app.route('/change-extension/<path:file_path>', methods=['POST'])
def change_extension(file_path):
    abs_path = os.path.join(ROOT_DIR, file_path)
    if not os.path.isfile(abs_path):
        return abort(404)

    new_ext = request.form['new_ext'].strip()
    base_name = os.path.splitext(abs_path)[0]
    new_path = base_name + new_ext

    try:
        os.rename(abs_path, new_path)
    except Exception as e:
        return f"Error renaming file: {e}", 500

    rel_new_path = os.path.relpath(new_path, ROOT_DIR).replace('\\', '/')
    return redirect(url_for('view_file', file_path=rel_new_path))

@app.route('/view/<path:file_path>')
def view_file(file_path):
    abs_path = os.path.join(ROOT_DIR, file_path)

    if not os.path.isfile(abs_path):
        return abort(404)

    mime_type, _ = mimetypes.guess_type(abs_path)
    ext = os.path.splitext(abs_path)[1].lower()
    streamable = ext in ['.mp4', '.webm', '.wav', '.ogg']
    image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']
    audio=[ '.mp3']

    preview_type = None
    if streamable:
        preview_type = 'video'
    elif ext in image_exts:
        preview_type = 'image'
    elif audio:
        preview_type="audio"

    return render_template("viewer.html", file_path=file_path, preview_type=preview_type)

@app.route('/raw/<path:file_path>')
def serve_file(file_path):
    abs_path = os.path.join(ROOT_DIR, file_path)
    if not os.path.isfile(abs_path):
        return abort(404)
    return send_file(abs_path, as_attachment=False)

@app.route('/stream/<path:file_path>')
def stream_media(file_path):
    abs_path = os.path.join(ROOT_DIR, file_path)
    if not os.path.isfile(abs_path):
        return abort(404)

    mime_type, _ = mimetypes.guess_type(abs_path)
    return send_file(abs_path, mimetype=mime_type)

@app.route('/download/<path:file_path>')
def download_file(file_path):
    abs_path = os.path.join(ROOT_DIR, file_path)
    if not os.path.isfile(abs_path):
        return abort(404)
    return send_file(abs_path, as_attachment=True)

@app.context_processor
def inject_globals():
    return {'os': os, 'ROOT_DIR': ROOT_DIR}



def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't have to be reachable
        s.connect(("10.255.255.255", 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = "127.0.0.1"
    finally:
        s.close()
    return IP

print("Access the app at:", f"http://{get_local_ip()}:4013")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=4013, debug=True)

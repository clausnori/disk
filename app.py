from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
import os
import shutil
from math import ceil

app = Flask(__name__)
app.secret_key = 'gggg'
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'pdf', 'txt', 'docx', 'xlsx', 'zip'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_stats():
    folders = get_folders()
    folder_count = len(folders)
    file_count = 0
    for folder in folders:
        file_count += len(get_files(folder))
    return {
        'folders': folder_count,
        'files': file_count
    }

def get_folders():
    return sorted([f for f in os.listdir(UPLOAD_FOLDER) if os.path.isdir(os.path.join(UPLOAD_FOLDER, f))])

def get_files(folder):
    folder_path = os.path.join(UPLOAD_FOLDER, folder)
    return sorted([f for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f))])

def get_disk_usage():
    total, used, free = shutil.disk_usage(UPLOAD_FOLDER)
    return {
        'total': total // (1024**2),
        'used': used // (1024**2),
        'free': free // (1024**2)
    }

@app.route('/')
def index():
    folders = get_folders()
    usage = get_disk_usage()
    stats = get_stats()
    return render_template('index.html', folders=folders, usage=usage, stats=stats)

@app.route('/folder/<folder>')
def view_folder(folder):
    page = request.args.get('page', 1, type=int)
    per_page = 20

    files = get_files(folder)
    usage = get_disk_usage()

    total_pages = ceil(len(files) / per_page)
    start = (page - 1) * per_page
    end = start + per_page
    files_paginated = files[start:end]

    return render_template('folder.html', folder=folder, files=files_paginated, usage=usage,
                           page=page, total_pages=total_pages)

@app.route('/create_folder', methods=['POST'])
def create_folder():
    folder_name = request.form['folder_name'].strip()
    if folder_name:
        path = os.path.join(UPLOAD_FOLDER, folder_name)
        try:
            os.makedirs(path)
            flash(f'Папка "{folder_name}" создана', 'success')
        except FileExistsError:
            flash('Папка уже существует', 'danger')
    return redirect(url_for('index'))

@app.route('/upload/<folder>', methods=['POST'])
def upload_file(folder):
    file = request.files.get('file')
    if not file or file.filename == '':
        flash('Файл не выбран', 'danger')
        return redirect(url_for('view_folder', folder=folder))
    if allowed_file(file.filename):
        folder_path = os.path.join(UPLOAD_FOLDER, folder)
        file.save(os.path.join(folder_path, file.filename))
        flash('Файл загружен', 'success')
    else:
        flash('Недопустимый формат файла', 'danger')
    return redirect(url_for('view_folder', folder=folder))

@app.route('/download/<folder>/<filename>')
def download_file(folder, filename):
    folder_path = os.path.join(UPLOAD_FOLDER, folder)
    return send_from_directory(folder_path, filename, as_attachment=True)

@app.route('/delete/<folder>/<filename>', methods=['POST'])
def delete_file(folder, filename):
    file_path = os.path.join(UPLOAD_FOLDER, folder, filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        flash('Файл удалён', 'success')
    else:
        flash('Файл не найден', 'danger')
    return redirect(url_for('view_folder', folder=folder))

if __name__ == '__main__':
    app.run(debug=True)
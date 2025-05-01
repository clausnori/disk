
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
import os
import shutil
import psutil

app = Flask(__name__)
app.secret_key = 'root'  # Для flash-сообщений
UPLOAD_FOLDER = 'static/images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[-1].lower() in ALLOWED_EXTENSIONS

def get_folders():
    return [f for f in os.listdir(UPLOAD_FOLDER) if os.path.isdir(os.path.join(UPLOAD_FOLDER, f))]

def get_images(folder):
    folder_path = os.path.join(UPLOAD_FOLDER, folder)
    return [f for f in os.listdir(folder_path) if allowed_file(f)]

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
    return render_template('index.html', folders=folders, usage=usage)

@app.route('/folder/<folder>')
def view_folder(folder):
    images = get_images(folder)
    usage = get_disk_usage()
    return render_template('folder.html', folder=folder, images=images, usage=usage)

@app.route('/create_folder', methods=['POST'])
def create_folder():
    folder_name = request.form['folder_name']
    path = os.path.join(UPLOAD_FOLDER, folder_name)
    try:
        os.makedirs(path)
        flash(f'Папка "{folder_name}" создана', 'success')
    except FileExistsError:
        flash('Папка уже существует', 'danger')
    return redirect(url_for('index'))

@app.route('/upload/<folder>', methods=['POST'])
def upload_file(folder):
    if 'file' not in request.files:
        flash('Нет файла в запросе', 'danger')
        return redirect(url_for('view_folder', folder=folder))
    file = request.files['file']
    if file.filename == '':
        flash('Файл не выбран', 'danger')
        return redirect(url_for('view_folder', folder=folder))
    if file and allowed_file(file.filename):
        save_path = os.path.join(UPLOAD_FOLDER, folder, file.filename)
        file.save(save_path)
        flash(f'Файл "{file.filename}" загружен', 'success')
    else:
        flash('Недопустимый формат файла', 'danger')
    return redirect(url_for('view_folder', folder=folder))

@app.route('/download/<folder>/<filename>')
def download_file(folder, filename):
    folder_path = os.path.join(UPLOAD_FOLDER, folder)
    return send_from_directory(folder_path, filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
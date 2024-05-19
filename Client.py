# Client side code
from flask import Flask, request, render_template, jsonify
import requests
import base64

app = Flask(__name__)


def send_data(images, operations, receiver_ip):
    url = f'http://{receiver_ip}:8000/receive_data'
    files = [('images', (image.filename, image.stream, image.mimetype)) for image in images]
    data = {'operations': operations}
    response = requests.post(url, files=files, data=data)
    if response.status_code == 200:
        return response.json()
    else:
        return None

@app.route('/status')
def status():
    url = 'http://4.221.187.23:8000/status'
    response = requests.post(url)
    if response.status_code == 200:
        return response.json()
    else:
        return jsonify({"error": "Failed to get status"}), response.status_code

@app.route('/')
def index():
    return render_template('upload_image.html', vmimg="/static/vm1.png")


@app.route('/process_image', methods=['POST'])
def process_image():
    images = request.files.getlist('images')
    operations = [request.form.get(f'operation_{i}') for i in range(len(images))]
    receiver_ip = "4.221.187.23"

    processed_images_data = send_data(images, operations, receiver_ip)
    if processed_images_data:
        processed_images = processed_images_data['images']
        return render_template('display_image.html', processed_images=processed_images)
    else:
        return "Failed to receive processed images."


if __name__ == '__main__':
    app.run(debug=True)

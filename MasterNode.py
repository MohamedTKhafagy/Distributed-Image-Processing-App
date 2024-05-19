# Master node code
import cv2
from flask import Flask, request, make_response, jsonify
import numpy as np
import threading
import io
import json
from azure.storage.queue import QueueClient
from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, BlobClient, generate_blob_sas, BlobSasPermissions
import socket
import time
import base64
import paramiko


app = Flask(__name__)
NumberOfWorkerNodes = 3

# Initialize Azure Queue service
ready_queue_client = QueueClient.from_connection_string(conn_str='DefaultEndpointsProtocol=https;AccountName=distributedimages;AccountKey=KJckN4UvM3AWc4+i2bvZbN64O8WYmFG9hIsaThQkmMAEkqneOXTjlVf75O8BlCovM7kjC/G8w6CC+ASt0+O1PQ==;EndpointSuffix=core.windows.net', queue_name='imageparts')
done_queue_client = QueueClient.from_connection_string(conn_str='DefaultEndpointsProtocol=https;AccountName=distributedimages;AccountKey=KJckN4UvM3AWc4+i2bvZbN64O8WYmFG9hIsaThQkmMAEkqneOXTjlVf75O8BlCovM7kjC/G8w6CC+ASt0+O1PQ==;EndpointSuffix=core.windows.net', queue_name='donequeue')

# Updates of nodes status
worker_status = {'worker1': 'down', 'worker2': 'down', 'worker3': 'down'}
worker_addresses = {'worker1': '10.1.1.7', 'worker2': '10.1.1.5', 'worker3': '10.1.1.6'}
status_lock = threading.Lock()

@app.route('/status', methods=['POST'])
def get_statuses():
    return jsonify(worker_status)

def listen_for_status_updates():
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.bind(('0.0.0.0', 9000))

    last_status_update_time = {}

    while True:
        data, addr = udp_sock.recvfrom(1024)
        message = data.decode('utf-8')

        if message.startswith('status:'):
            _, received_ip, status = message.split(':')
            worker_name = None
            for name, ip in worker_addresses.items():
                if ip == received_ip:
                    worker_name = name
                    break
            if worker_name:
                with status_lock:
                    worker_status[worker_name] = status
                    last_status_update_time[worker_name] = time.time()

        current_time = time.time()
        for worker_name, last_update_time in last_status_update_time.items():
            if current_time - last_update_time > 1:
                with status_lock:
                    worker_status[worker_name] = 'down'




def check_and_restart_workers():
    time.sleep(10)
    global worker_status
    while True:
        for worker, status in worker_status.items():
            if status == 'down':
                print(f"{worker} is down. Attempting to restart...")
                restart_worker(worker)
        time.sleep(3)


def restart_worker(hostname):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(hostname)
        stdin, stdout, stderr = ssh.exec_command('cd cloud && python3 worker3.py')
        # Optionally read stdout and stderr for logging or debugging
        stdout_output = stdout.read().decode()
        stderr_output = stderr.read().decode()

        if stdout_output:
            print(f"Output from {hostname}:")
            print(stdout_output)

        if stderr_output:
            print(f"Errors from {hostname}:")
            print(stderr_output)

    except Exception as e:
        print(f"Failed to restart worker on {hostname}: {e}")
    finally:
        ssh.close()


response_counter = 0
response_lock = threading.Lock()
processed_segments = []

blob_service_client = BlobServiceClient.from_connection_string('DefaultEndpointsProtocol=https;AccountName=distributedimages;AccountKey=KJckN4UvM3AWc4+i2bvZbN64O8WYmFG9hIsaThQkmMAEkqneOXTjlVf75O8BlCovM7kjC/G8w6CC+ASt0+O1PQ==;EndpointSuffix=core.windows.net')
container_name = 'bigimages'
container_client = blob_service_client.get_container_client(container_name)

def generate_sas_token(account_name, account_key, container_name, blob_name):
    expiry_time = datetime.utcnow() + timedelta(hours=1)
    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container_name,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True, add=True, delete=True),
        expiry=expiry_time
    )
    return sas_token

def divide_image(image_file, name, operation):
    img = image_file.read()
    nparr = np.frombuffer(img, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    segments = np.array_split(img, NumberOfWorkerNodes, axis=0)

    for i, segment in enumerate(segments):
        _, buffer = cv2.imencode('.jpg', segment)
        segment_data = buffer.tobytes()
        blob_name = f'segment_{i}_{name}.jpg'
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(segment_data, overwrite=True)

        sas_token = generate_sas_token(account_name='distributedimages', account_key='KJckN4UvM3AWc4+i2bvZbN64O8WYmFG9hIsaThQkmMAEkqneOXTjlVf75O8BlCovM7kjC/G8w6CC+ASt0+O1PQ==', container_name=container_name, blob_name=blob_name)
        blob_url_with_sas = f"{blob_client.url}?{sas_token}"

        message_content = {
            'operation': operation,
            'index': i,
            'blob_url': blob_url_with_sas,
            'name': name,
            'segmented': 'yes'
        }
        ready_queue_client.send_message(json.dumps(message_content))

@app.route('/receive_data', methods=['POST'])
def handle_post():
    images = request.files.getlist('images')
    operations = request.form.getlist('operations')
    num_images = len(images)

    response_counter = 0
    processed_images = []

    if num_images == 1:
        divide_image(images[0], images[0].filename, operations[0])
    else:
        for i, image in enumerate(images):
            blob_name = f'image_{i}_{image.filename}.jpg'
            blob_client = container_client.get_blob_client(blob_name)
            blob_client.upload_blob(image.read(), overwrite=True)

            sas_token = generate_sas_token(account_name='distributedimages', account_key='KJckN4UvM3AWc4+i2bvZbN64O8WYmFG9hIsaThQkmMAEkqneOXTjlVf75O8BlCovM7kjC/G8w6CC+ASt0+O1PQ==', container_name=container_name, blob_name=blob_name)
            blob_url_with_sas = f"{blob_client.url}?{sas_token}"

            message_content = {
                'operation': operations[i],
                'index': i,
                'blob_url': blob_url_with_sas,
                'name': image.filename,
                'segmented': 'no'
            }
            ready_queue_client.send_message(json.dumps(message_content))

    processed_images_data = []

    while response_counter < (NumberOfWorkerNodes if num_images == 1 else num_images):
        messages = done_queue_client.receive_messages(messages_per_page=NumberOfWorkerNodes, visibility_timeout=5)
        for message in messages:
            content = json.loads(message.content)
            index = content['index']
            blob_url = content['blob_url']
            image_name = content['name']
            blob_client = BlobClient.from_blob_url(blob_url)
            segment_data = blob_client.download_blob().readall()
            nparr = np.frombuffer(segment_data, np.uint8)
            processed_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            # Append the index and processed image to the list
            processed_images_data.append((index, processed_image, image_name))

            with response_lock:
                response_counter += 1

            done_queue_client.delete_message(message.id, message.pop_receipt)

    # Sort the processed images based on their index
    processed_images_data.sort(key=lambda x: x[0])
    processed_images = [data[1] for data in processed_images_data]
    image_names = [data[2] for data in processed_images_data]


    if num_images == 1:
        if operations[0] == 'Rotate':
            processed_images = processed_images[::-1]
        processed_image = cv2.vconcat(processed_images)
        _, encoded_image = cv2.imencode('.jpg', processed_image)
        image_base64 = base64.b64encode(encoded_image).decode('utf-8')

        # Create a JSON response containing the base64 encoded image
        return jsonify({'images': [{'name': image_names[0], 'data': image_base64}]})
    else:
        encoded_images = [{'name': name, 'data': base64.b64encode(cv2.imencode('.jpg', img)[1]).decode('utf-8')} for
                          img, name in zip(processed_images, image_names)]
        return jsonify({'images': encoded_images})
if __name__ == '__main__':
    status_thread = threading.Thread(target=listen_for_status_updates, daemon=True)
    status_thread.start()
    fault_recovery_thread = threading.Thread(target=check_and_restart_workers, daemon=True)
    fault_recovery_thread.start()
    app.run('0.0.0.0', port=8000)

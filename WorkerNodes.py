import cv2
import numpy as np
import json
from azure.storage.queue import QueueClient
from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, BlobClient, generate_blob_sas, BlobSasPermissions
import threading
import socket
import time

# Initialize Azure Queue services
ready_queue_client = QueueClient.from_connection_string(conn_str='DefaultEndpointsProtocol=https;AccountName=distributedimages;AccountKey=KJckN4UvM3AWc4+i2bvZbN64O8WYmFG9hIsaThQkmMAEkqneOXTjlVf75O8BlCovM7kjC/G8w6CC+ASt0+O1PQ==;EndpointSuffix=core.windows.net', queue_name='imageparts')
done_queue_client = QueueClient.from_connection_string(conn_str='DefaultEndpointsProtocol=https;AccountName=distributedimages;AccountKey=KJckN4UvM3AWc4+i2bvZbN64O8WYmFG9hIsaThQkmMAEkqneOXTjlVf75O8BlCovM7kjC/G8w6CC+ASt0+O1PQ==;EndpointSuffix=core.windows.net', queue_name='donequeue')

blob_service_client = BlobServiceClient.from_connection_string('DefaultEndpointsProtocol=https;AccountName=distributedimages;AccountKey=KJckN4UvM3AWc4+i2bvZbN64O8WYmFG9hIsaThQkmMAEkqneOXTjlVf75O8BlCovM7kjC/G8w6CC+ASt0+O1PQ==;EndpointSuffix=core.windows.net')
container_name = 'bigimages'
container_client = blob_service_client.get_container_client(container_name)

global status
status_lock = threading.Lock()
hostname = socket.gethostname()
worker_ip = socket.gethostbyname(hostname)

operation_mapping = {
    "Edge Detection": "edge_detection",
    "Color Inversion": "color_inversion",
    "Rotate": "rotate",
    "Blur": "blur",
    "Grayscale": "grayscale"
}
def send_status_update():
    global status
    status = 'ready'
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    while True:
        with status_lock:
            message = f"status:{worker_ip}:{status}"
            udp_sock.sendto(message.encode('utf-8'), ('10.1.1.4', 9000))
        time.sleep(0.3)

def generate_sas_token(account_name, account_key, container_name, blob_name):
    expiry_time = datetime.utcnow() + timedelta(hours=1)  # SAS token valid for 1 hour
    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container_name,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True, add=True, delete=True),  # Permissions updated
        expiry=expiry_time
    )
    return sas_token

def process_image_segment():
    global status
    messages = ready_queue_client.receive_messages(messages_per_page=1, visibility_timeout=30)  # Increased visibility timeout

    for message in messages:
        content = json.loads(message.content)
        operation = content['operation']
        operation = operation_mapping[operation]
        index = content['index']
        blob_url = content['blob_url']
        name = content['name']
        segmented = content['segmented']
        with status_lock:
            status = 'busy'

        try:
            # Download the image segment from Blob Storage
            blob_client = BlobClient.from_blob_url(blob_url)
            segment_data = blob_client.download_blob().readall()

            # Decode the image segment
            img = cv2.imdecode(np.frombuffer(segment_data, np.uint8), cv2.IMREAD_COLOR)

            # Perform the specified operation
            if operation == 'edge_detection':
                result = cv2.Canny(img, 100, 200)
            elif operation == 'color_inversion':
                result = cv2.bitwise_not(img)
            elif operation == 'blur':
                result = cv2.GaussianBlur(img, (15, 15), 0)
            elif operation == 'rotate':
                height, width = img.shape[:2]
                rotation_matrix = cv2.getRotationMatrix2D((width / 2, height / 2), 180, 1)  # Rotate by 180 degrees
                result = cv2.warpAffine(img, rotation_matrix, (width, height))
            elif operation == 'grayscale':
                result = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                raise ValueError("Unknown operation")

            # Encode the processed image to JPEG format
            _, encoded_image = cv2.imencode('.jpg', result)
            processed_segment_data = encoded_image.tobytes()

            # Upload the processed segment to Blob Storage
            if segmented == 'yes':
                processed_blob_name = f'processed_segment_{index}_{name}.jpg'
            else:
                processed_blob_name = f'processed_image_{index}_{name}.jpg'
            processed_blob_client = container_client.get_blob_client(processed_blob_name)
            processed_blob_client.upload_blob(processed_segment_data, overwrite=True)

            # Generate SAS token for the processed blob
            sas_token = generate_sas_token(account_name='distributedimages', account_key='KJckN4UvM3AWc4+i2bvZbN64O8WYmFG9hIsaThQkmMAEkqneOXTjlVf75O8BlCovM7kjC/G8w6CC+ASt0+O1PQ==', container_name=container_name, blob_name=processed_blob_name)
            blob_url_with_sas = f"{processed_blob_client.url}?{sas_token}"

            response_content = {
                'index': index,
                'blob_url': blob_url_with_sas,
                'name': processed_blob_name
            }

            # Send the processed segment URL back through the response queue
            done_queue_client.send_message(json.dumps(response_content))

            # Delete the original segment blob
            blob_client.delete_blob()

            # Delete the message from the queue
            ready_queue_client.delete_message(message.id, message.pop_receipt)
        except Exception as e:
            print(f"Error processing image segment: {e}")
        finally:
            with status_lock:
                status = 'ready'

if __name__ == '__main__':
    # Start the status update thread
    status_thread = threading.Thread(target=send_status_update, daemon=True)
    status_thread.start()

    while True:
        process_image_segment()

"""ARCHIVED one-shot NAO camera-file download using Paramiko/SFTP.

Prompts for the NAO password, selects the newest JPG in the robot's
camera folder, and stores it locally. This is not session-aware, and
it disables SSH host-key verification (legacy behavior; review before reuse).
"""

import paramiko
import os

NAO_IP = "169.254.247.199"
NAO_USER = "nao"

REMOTE_FOLDER = "/home/nao/recordings/cameras/"
LOCAL_FOLDER = "data/nao_frames"

password = input("NAO password: ")

ssh = paramiko.SSHClient()
# Legacy connection accepts unknown host keys; not recommended for deployment.
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

ssh.connect(
    NAO_IP,
    username=NAO_USER,
    password=password
)

sftp = ssh.open_sftp()

files = sftp.listdir_attr(REMOTE_FOLDER)

images = [
    f for f in files
    if f.filename.lower().endswith(".jpg")
]

# Newest file by remote modification time; assumes at least one JPG exists.
latest = max(images, key=lambda f: f.st_mtime)

remote_path = REMOTE_FOLDER + latest.filename
local_path = os.path.join(LOCAL_FOLDER, latest.filename)

os.makedirs(LOCAL_FOLDER, exist_ok=True)

sftp.get(remote_path, local_path)

sftp.close()
ssh.close()

print("New NAO image saved:")
print(local_path)
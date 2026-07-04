import paramiko
import os
import threading
import time

class SSHClientWrapper:
    def __init__(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.connected = False
        self.comfy_root = ""

    def connect(self, host, port, username, password, key_filename, passphrase=None):
        if passphrase == "":
            passphrase = None
        try:
            if key_filename and os.path.exists(key_filename):
                self.client.connect(hostname=host, port=port, username=username, key_filename=key_filename, passphrase=passphrase, timeout=10)
            else:
                self.client.connect(hostname=host, port=port, username=username, password=password, timeout=10)
            self.connected = True
            return True, "Connected successfully"
        except Exception as e:
            self.connected = False
            return False, str(e)

    def disconnect(self):
        if self.connected:
            self.client.close()
            self.connected = False

    def execute_command(self, command):
        if not self.connected:
            return False, "Not connected"
        try:
            stdin, stdout, stderr = self.client.exec_command(command)
            return True, stdout.read().decode('utf-8').strip()
        except Exception as e:
            return False, str(e)

    def find_comfy_root(self):
        success, out = self.execute_command("find /workspace /home /root -name ComfyUI -type d -maxdepth 3 2>/dev/null | head -n 1")
        if success and out:
            self.comfy_root = out
            return out
        return ""

    def get_disk_space(self):
        # Returns free space on root or workspace
        success, out = self.execute_command("df -h /workspace 2>/dev/null || df -h /")
        if success and out:
            lines = out.split('\n')
            if len(lines) > 1:
                parts = lines[1].split()
                if len(parts) >= 4:
                    return parts[3] # Avail space
        return "Unknown"

    def list_model_folders(self):
        if not self.comfy_root:
            return []
        success, out = self.execute_command(f"ls -1 '{self.comfy_root}/models/'")
        if success and out:
            return [x for x in out.split('\n') if x]
        return []

    def scan_models(self):
        if not self.connected or not self.comfy_root:
            return []
            
        cmd = f"find '{self.comfy_root}/models/' -type f \\( -name \"*.safetensors\" -o -name \"*.pt\" -o -name \"*.pth\" -o -name \"*.bin\" \\) -printf \"%p|%s\\n\""
        success, out = self.execute_command(cmd)
        
        models = []
        if success and out:
            prefix = f"{self.comfy_root}/models/"
            for line in out.split('\n'):
                line = line.strip()
                if line.startswith(prefix) and '|' in line:
                    path_part, size_part = line.split('|', 1)
                    rel_path = path_part[len(prefix):]
                    parts = rel_path.split('/')
                    if len(parts) >= 2:
                        folder = parts[0]
                        filename = parts[-1]
                        
                        try:
                            size_bytes = int(size_part)
                            if size_bytes >= 1024**3:
                                size_str = f"{size_bytes / (1024**3):.2f} GB"
                            elif size_bytes >= 1024**2:
                                size_str = f"{size_bytes / (1024**2):.2f} MB"
                            else:
                                size_str = f"{size_bytes / 1024:.2f} KB"
                        except:
                            size_str = ""
                            size_bytes = 0
                            
                        models.append({'folder': folder, 'filename': filename, 'size': size_str, 'size_bytes': size_bytes})
        return models



    def check_file_exists(self, filepath):
        success, out = self.execute_command(f"test -f '{filepath}' && echo 'EXISTS' || echo 'MISSING'")
        return out == 'EXISTS'

    def move_file(self, old_folder, old_filename, new_folder, new_filename):
        if not self.comfy_root:
            return False, "Not connected"
        old_path = f"{self.comfy_root}/models/{old_folder}/{old_filename}"
        new_path = f"{self.comfy_root}/models/{new_folder}/{new_filename}"
        success, out = self.execute_command(f"mv '{old_path}' '{new_path}'")
        return success, out

    def cancel_download(self):
        if hasattr(self, 'current_download_sftp') and self.current_download_sftp:
            try:
                self.upload_cancelled = True
                self.current_download_sftp.close()
            except:
                pass
        if hasattr(self, 'current_download_channel') and self.current_download_channel:
            try:
                self.current_download_channel.close()
            except:
                pass

    def download_file(self, url, folder, filename, token, progress_callback, completion_callback):
        if not self.comfy_root:
            completion_callback(False, "ComfyUI root not found")
            return

        filepath = f"{self.comfy_root}/models/{folder}/{filename}"
        
        # Python script to run on remote server
        py_script = """
import urllib.request
import time
import sys
import os

url = sys.argv[1]
path = sys.argv[2]
token = sys.argv[3] if len(sys.argv) > 3 else ""

headers = {'User-Agent': 'Mozilla/5.0'}
if token:
    headers['Authorization'] = f'Bearer {token}'

downloaded = 0
if os.path.exists(path):
    downloaded = os.path.getsize(path)

try:
    remote_size = 0
    try:
        head_req = urllib.request.Request(url, headers=headers, method='HEAD')
        with urllib.request.urlopen(head_req) as resp:
            remote_size = int(resp.info().get('Content-Length', 0))
    except: pass
    
    if remote_size > 0 and downloaded > 0 and downloaded == remote_size:
        print("DONE:AlreadyExists", flush=True)
        sys.exit(0)
        
    if downloaded > 0:
        headers['Range'] = f'bytes={downloaded}-'

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as response:
        is_partial = response.status == 206
        mode = 'ab' if is_partial and downloaded > 0 else 'wb'
        if not is_partial:
            downloaded = 0
            
        with open(path, mode) as out_file:
            content_length = response.info().get('Content-Length')
            remaining = int(content_length.strip()) if content_length else 0
            total_size = downloaded + remaining
            initial_downloaded = downloaded
            
            chunk_size = 1024 * 1024 * 5 # 5MB
            start_time = time.time()
            
            while True:
                chunk = response.read(chunk_size)
                if not chunk: break
                out_file.write(chunk)
                downloaded += len(chunk)
                elapsed = time.time() - start_time
                speed = (downloaded - initial_downloaded) / elapsed if elapsed > 0 else 0
                print(f"PROGRESS:{downloaded}:{total_size}:{speed}", flush=True)
                
    print("DONE:Success", flush=True)
except urllib.error.HTTPError as e:
    if e.code == 416: # Range Not Satisfiable (Already fully downloaded)
        print("DONE:AlreadyExists", flush=True)
    else:
        print(f"DONE:Error: HTTP {e.code} - {str(e)}", flush=True)
except Exception as e:
    print(f"DONE:Error: {str(e)}", flush=True)
"""
        
        def run():
            try:
                # Escape quotes in script
                script_b64 = py_script.encode('utf-8').hex()
                remote_cmd = f"mkdir -p \"$(dirname '{filepath}')\" && python3 -u -c \"import binascii; exec(binascii.unhexlify('{script_b64}').decode('utf-8'))\" '{url}' '{filepath}' '{token}'"
                
                stdin, stdout, stderr = self.client.exec_command(remote_cmd)
                self.current_download_channel = stdout.channel
                
                for line in iter(stdout.readline, ""):
                    line = line.strip()
                    if line.startswith("PROGRESS:"):
                        parts = line.split(":")
                        if len(parts) >= 4:
                            down = int(parts[1])
                            total = int(parts[2])
                            speed = float(parts[3])
                            progress_callback(down, total, speed)
                    elif line.startswith("DONE:"):
                        if "Success" in line:
                            completion_callback(True, "Downloaded successfully")
                        elif "AlreadyExists" in line:
                            completion_callback(True, "AlreadyExists")
                        else:
                            completion_callback(False, line)
                        return
                
                err = stderr.read().decode('utf-8')
                if err:
                    completion_callback(False, err)
                else:
                    completion_callback(False, "Connection closed unexpectedly")
            except Exception as e:
                completion_callback(False, str(e))
            finally:
                self.current_download_channel = None
                
        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()

    def upload_file(self, local_path, folder, filename, progress_callback, completion_callback):
        if not self.connected or not self.comfy_root:
            completion_callback(False, "Not connected")
            return
            
        def run():
            sftp = None
            try:
                remote_dir = f"{self.comfy_root}/models/{folder}"
                self.execute_command(f"mkdir -p '{remote_dir}'")
                remote_path = f"{remote_dir}/{filename}"
                
                sftp = self.client.open_sftp()
                self.current_download_sftp = sftp
                
                remote_size = 0
                try:
                    stat = sftp.stat(remote_path)
                    remote_size = stat.st_size
                except IOError:
                    pass
                
                local_size = os.path.getsize(local_path)
                if remote_size > 0:
                    if remote_size == local_size:
                        completion_callback(True, "AlreadyExists")
                        return
                    elif remote_size > local_size:
                        # Remote file is larger, overwrite it completely
                        remote_size = 0
                
                start_time = time.time()
                initial_remote_size = remote_size
                
                mode = 'a' if remote_size > 0 else 'w'
                with open(local_path, 'rb') as lf, sftp.open(remote_path, mode) as rf:
                    rf.set_pipelined(True)
                    if remote_size > 0:
                        lf.seek(remote_size)
                        rf.seek(remote_size)
                        
                    last_update = time.time()
                    while True:
                        if getattr(self, 'upload_cancelled', False):
                            raise Exception("Upload paused")
                            
                        chunk = lf.read(32768)
                        if not chunk:
                            break
                        rf.write(chunk)
                        remote_size += len(chunk)
                        
                        now = time.time()
                        if now - last_update >= 0.2:
                            elapsed = now - start_time
                            speed = (remote_size - initial_remote_size) / elapsed if elapsed > 0 else 0
                            progress_callback(remote_size, local_size, speed)
                            last_update = now
                            
                    # Final update
                    elapsed = time.time() - start_time
                    speed = (remote_size - initial_remote_size) / elapsed if elapsed > 0 else 0
                    progress_callback(remote_size, local_size, speed)
                        
                completion_callback(True, "Uploaded successfully")
            except Exception as e:
                completion_callback(False, str(e))
            finally:
                if sftp:
                    sftp.close()
                self.current_download_sftp = None
                self.upload_cancelled = False
                
        self.upload_cancelled = False
        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()

    def delete_file(self, folder, filename):
        if not self.connected or not self.comfy_root:
            return False, "Not connected"
        try:
            filepath = f"{self.comfy_root}/models/{folder}/{filename}"
            # Обнуляем файл перед удалением, чтобы мгновенно освободить место, 
            # даже если ComfyUI держит его открытым в памяти
            self.client.exec_command(f"> '{filepath}'")
            
            remote_cmd = f"rm -f '{filepath}'"
            stdin, stdout, stderr = self.client.exec_command(remote_cmd)
            err = stderr.read().decode('utf-8')
            if err:
                return False, err
            return True, ""
        except Exception as e:
            return False, str(e)

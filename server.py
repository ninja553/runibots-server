from flask import Flask, request, jsonify
import os
import requests
from datetime import datetime, timedelta
import time
import base64
from threading import Lock

app = Flask(__name__)

# Configuración de GitHub
GITHUB_REPO = os.getenv("GITHUB_REPO", "ninja553/runibots-data")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_AUTHORIZED_IDS_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/authorized_ids.txt"
GITHUB_HARDWARE_IDS_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/hardware_ids.txt"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents"

# Clave secreta para autorización (valor por defecto temporal)
ADMIN_KEY = os.getenv("ADMIN_KEY", "tu_clave_secreta_admin")

# URL del webhook de Discord
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1366414104171909191/d4McCwAD6pct0DAeF18gNIN6iD6B50tjRtqyQtnsf_l4dTnL_bM9T6EacyS3qDarOrj5"

# Archivos locales
HARDWARE_IDS_FILE = "hardware_ids.txt"
AUTHORIZED_IDS_FILE = "authorized_ids.txt"

# Asegurarse de que los archivos existan
if not os.path.exists(HARDWARE_IDS_FILE):
    with open(HARDWARE_IDS_FILE, "w") as f:
        pass

if not os.path.exists(AUTHORIZED_IDS_FILE):
    with open(AUTHORIZED_IDS_FILE, "w") as f:
        f.write("hardware_id,fecha_autorizacion,dias_validez\n")

# Diccionario para rastrear actividad e instancias
client_activity = {}
INACTIVITY_THRESHOLD = 840  # 14 minutos en segundos

# Bloqueo para manejar concurrencia
file_lock = Lock()

def download_file(url, local_file):
    """Descarga un archivo desde GitHub si no existe localmente."""
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        with open(local_file, 'w') as f:
            f.write(response.text)
        print(f"Descargado {local_file} desde GitHub")
    except Exception as e:
        print(f"Error al descargar {local_file}: {e}")

def upload_file(local_file, github_path):
    """Sube un archivo a GitHub."""
    with file_lock:
        try:
            # Leer el archivo local
            with open(local_file, 'r') as f:
                content = f.read()
            
            # Codificar contenido en base64
            content_b64 = base64.b64encode(content.encode()).decode()
            
            # Obtener el SHA del archivo existente (si existe)
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
            response = requests.get(f"{GITHUB_API_URL}/{github_path}", headers=headers)
            sha = None
            if response.status_code == 200:
                sha = response.json().get("sha")
            elif response.status_code != 404:
                response.raise_for_status()
            
            # Subir el archivo
            payload = {
                "message": f"Update {github_path}",
                "content": content_b64,
                "branch": "main"
            }
            if sha:
                payload["sha"] = sha
            
            response = requests.put(f"{GITHUB_API_URL}/{github_path}", headers=headers, json=payload)
            response.raise_for_status()
            print(f"Archivo {github_path} subido a GitHub")
        except Exception as e:
            print(f"Error al subir {github_path} a GitHub: {e}")

# Descargar archivos al iniciar
download_file(GITHUB_AUTHORIZED_IDS_URL, AUTHORIZED_IDS_FILE)
download_file(GITHUB_HARDWARE_IDS_URL, HARDWARE_IDS_FILE)

def send_to_discord(message):
    """Envía un mensaje al webhook de Discord con depuración."""
    try:
        discord_payload = {"content": message}
        response = requests.post(DISCORD_WEBHOOK_URL, json=discord_payload)
        response.raise_for_status()
        print(f"Mensaje enviado a Discord: {message}")
    except Exception as e:
        print(f"Error al enviar mensaje a Discord: {e}")

@app.route('/submit_hardware_id', methods=['POST'])
def submit_hardware_id():
    try:
        data = request.get_json()
        hardware_id = data.get('hardware_id')
        instance_id = data.get('instance_id')
        if not hardware_id or not instance_id:
            return jsonify({"status": "error", "message": "Falta hardware_id o instance_id"}), 400

        with file_lock:
            with open(HARDWARE_IDS_FILE, "a") as f:
                f.write(hardware_id + "\n")
            upload_file(HARDWARE_IDS_FILE, "hardware_ids.txt")
        
        send_to_discord(f"Nuevo hardware_id recibido: `{hardware_id}`, instance_id: `{instance_id}`")
        
        # Registrar actividad inicial
        if hardware_id not in client_activity:
            client_activity[hardware_id] = {"status": "active", "last_activity": time.time(), "instances": {}}
        client_activity[hardware_id]["instances"][instance_id] = time.time()
        client_activity[hardware_id]["status"] = "active"
        client_activity[hardware_id]["last_activity"] = time.time()

        return jsonify({"status": "success", "message": "hardware_id recibido"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/verify', methods=['POST'])
def verify():
    try:
        data = request.get_json()
        hardware_id = data.get('hardware_id')
        instance_id = data.get('instance_id')
        if not hardware_id or not instance_id:
            return jsonify({"status": "error", "message": "Falta hardware_id o instance_id"}), 400

        with file_lock:
            download_file(GITHUB_AUTHORIZED_IDS_URL, AUTHORIZED_IDS_FILE)
            authorized_ids = []
            with open(AUTHORIZED_IDS_FILE, "r") as f:
                content = f.readlines()
                print(f"Contenido de {AUTHORIZED_IDS_FILE}: {content}")
                for line in content[1:]:  # Saltar encabezado
                    if line.strip():
                        parts = line.strip().split(",")
                        if len(parts) == 3:
                            auth_hardware_id, auth_date, validity_days = parts
                            print(f"Comparando {auth_hardware_id} con {hardware_id}")
                            if auth_hardware_id == hardware_id:
                                try:
                                    auth_date = datetime.strptime(auth_date, "%Y-%m-%d")
                                    validity_days = int(validity_days)
                                    expiration_date = auth_date + timedelta(days=validity_days)
                                    current_date = datetime.now()
                                    print(f"Fecha actual: {current_date}, Expiración: {expiration_date}")
                                    if current_date <= expiration_date:
                                        authorized_ids.append({
                                            "hardware_id": auth_hardware_id,
                                            "fecha_autorizacion": auth_date.strftime("%Y-%m-%d"),
                                            "dias_validez": validity_days,
                                            "fecha_expiracion": expiration_date.strftime("%Y-%m-%d")
                                        })
                                        # Actualizar actividad
                                        if hardware_id not in client_activity:
                                            client_activity[hardware_id] = {"status": "active", "last_activity": time.time(), "instances": {}}
                                        client_activity[hardware_id]["instances"][instance_id] = time.time()
                                        client_activity[hardware_id]["status"] = "active"
                                        client_activity[hardware_id]["last_activity"] = time.time()
                                except ValueError as e:
                                    print(f"Error al parsear fecha: {e}")
                                    continue

        if authorized_ids:
            return jsonify({
                "status": "success",
                "message": "Autorizado",
                "expiration": authorized_ids[0]["fecha_expiracion"]
            }), 200
        else:
            return jsonify({"status": "error", "message": "No autorizado o autorización expirada"}), 403
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/authorize', methods=['POST'])
def authorize():
    try:
        data = request.get_json()
        hardware_id = data.get('hardware_id')
        validity_days = data.get('validity_days')
        admin_key = data.get('admin_key')
        if not hardware_id or not validity_days or not admin_key:
            return jsonify({"status": "error", "message": "Falta hardware_id, validity_days o admin_key"}), 400

        if admin_key != ADMIN_KEY:
            return jsonify({"status": "error", "message": "Invalid admin_key"}), 403

        with file_lock:
            download_file(GITHUB_AUTHORIZED_IDS_URL, AUTHORIZED_IDS_FILE)
            current_date = datetime.now().strftime("%Y-%m-%d")
            with open(AUTHORIZED_IDS_FILE, "a") as f:
                f.write(f"{hardware_id},{current_date},{validity_days}\n")
            upload_file(AUTHORIZED_IDS_FILE, "authorized_ids.txt")
        
        send_to_discord(f"Hardware_id autorizado: `{hardware_id}`, válidez: {validity_days} días")
        return jsonify({"status": "success", "message": "hardware_id authorized", "validity_days": validity_days}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/get_hardware_ids", methods=["GET"])
def get_hardware_ids():
    try:
        with file_lock:
            download_file(GITHUB_HARDWARE_IDS_URL, HARDWARE_IDS_FILE)
            with open(HARDWARE_IDS_FILE, "r") as f:
                hardware_ids = [line.strip() for line in f if line.strip()]
        return jsonify({"status": "success", "hardware_ids": hardware_ids}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/get_authorized_ids", methods=["GET"])
def get_authorized_ids():
    try:
        with file_lock:
            download_file(GITHUB_AUTHORIZED_IDS_URL, AUTHORIZED_IDS_FILE)
            authorized_ids = []
            with open(AUTHORIZED_IDS_FILE, "r") as f:
                lines = f.readlines()
                for line in lines[1:]:  # Saltar encabezado
                    if line.strip():
                        parts = line.strip().split(",")
                        if len(parts) == 3:
                            hardware_id, auth_date, validity_days = parts
                            try:
                                auth_date = datetime.strptime(auth_date, "%Y-%m-%d")
                                validity_days = int(validity_days)
                                expiration_date = auth_date + timedelta(days=validity_days)
                                if datetime.now() <= expiration_date:
                                    authorized_ids.append({
                                        "hardware_id": hardware_id,
                                        "fecha_autorizacion": auth_date.strftime("%Y-%m-%d"),
                                        "dias_validez": validity_days,
                                        "fecha_expiracion": expiration_date.strftime("%Y-%m-%d")
                                    })
                            except ValueError:
                                continue
        return jsonify({"status": "success", "authorized_ids": authorized_ids}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/revoke", methods=["POST"])
def revoke():
    try:
        data = request.get_json()
        hardware_id = data.get("hardware_id")
        admin_key = data.get("admin_key")
        if not hardware_id or not admin_key:
            return jsonify({"status": "error", "message": "hardware_id and admin_key are required"}), 400

        if admin_key != ADMIN_KEY:
            return jsonify({"status": "error", "message": "Invalid admin_key"}), 403

        with file_lock:
            download_file(GITHUB_AUTHORIZED_IDS_URL, AUTHORIZED_IDS_FILE)
            lines = []
            with open(AUTHORIZED_IDS_FILE, "r") as f:
                lines = f.readlines()
            with open(AUTHORIZED_IDS_FILE, "w") as f:
                for line in lines:
                    if line.strip() and not line.startswith(f"{hardware_id},"):
                        f.write(line)
            upload_file(AUTHORIZED_IDS_FILE, "authorized_ids.txt")
        
        # Actualizar client_activity
        if hardware_id in client_activity:
            client_activity[hardware_id]["status"] = "inactive"
            client_activity[hardware_id]["instances"] = {}
        
        send_to_discord(f"Hardware_id revocado: `{hardware_id}`")
        return jsonify({"status": "success", "message": f"hardware_id {hardware_id} revoked"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/report_activity', methods=['POST'])
def report_activity():
    try:
        data = request.get_json()
        hardware_id = data.get('hardware_id')
        instance_id = data.get('instance_id')
        status = data.get('status')
        if not hardware_id or not instance_id or not status:
            return jsonify({"status": "error", "message": "Falta hardware_id, instance_id o status"}), 400

        with file_lock:
            download_file(GITHUB_AUTHORIZED_IDS_URL, AUTHORIZED_IDS_FILE)
            authorized = False
            with open(AUTHORIZED_IDS_FILE, "r") as f:
                lines = f.readlines()
                for line in lines[1:]:  # Saltar encabezado
                    if line.strip():
                        parts = line.strip().split(",")
                        if len(parts) == 3 and parts[0] == hardware_id:
                            auth_date = datetime.strptime(parts[1], "%Y-%m-%d")
                            validity_days = int(parts[2])
                            expiration_date = auth_date + timedelta(days=validity_days)
                            if datetime.now() <= expiration_date:
                                authorized = True
                                break

        if not authorized:
            return jsonify({"status": "error", "message": "No autorizado o autorización expirada"}), 403

        # Actualizar client_activity
        if hardware_id not in client_activity:
            client_activity[hardware_id] = {"status": "active", "last_activity": time.time(), "instances": {}}
        
        if status == "active":
            client_activity[hardware_id]["instances"][instance_id] = time.time()
            client_activity[hardware_id]["status"] = "active"
            client_activity[hardware_id]["last_activity"] = time.time()
        elif status == "inactive":
            if instance_id in client_activity[hardware_id]["instances"]:
                del client_activity[hardware_id]["instances"][instance_id]
            if not client_activity[hardware_id]["instances"]:
                client_activity[hardware_id]["status"] = "inactive"

        return jsonify({"status": "success", "message": "Actividad reportada"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/active_clients', methods=['GET'])
def active_clients():
    try:
        current_time = time.time()
        clients = []
        for hardware_id, info in client_activity.items():
            if (current_time - info["last_activity"]) > INACTIVITY_THRESHOLD:
                info["status"] = "inactive"
                info["instances"] = {}
            
            clients.append({
                "hardware_id": hardware_id,
                "status": info["status"],
                "last_activity": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(info["last_activity"])),
                "instance_count": len(info["instances"]),
                "instances": list(info["instances"].keys())
            })
        
        return jsonify({"clients": clients}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

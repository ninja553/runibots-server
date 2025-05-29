from flask import Flask, request, jsonify
import time
import os
from datetime import datetime, timedelta
import requests

app = Flask(__name__)

# Archivo para almacenar hardware_ids autorizados
AUTHORIZED_FILE = "authorized_ids.txt"

# URL del archivo authorized_ids.txt en GitHub (raw)
GITHUB_REPO = os.getenv("GITHUB_REPO", "ninja553/runibots-data")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_AUTHORIZED_IDS_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/authorized_ids.txt"

# Webhook de Discord
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1366414104171909191/d4McCwAD6pct0DAeF18gNIN6iD6B50tjRtqyQtnsf_l4dTnL_bM9T6EacyS3qDarOrj5"

# Diccionario para rastrear el estado de actividad e instancias
client_activity = {}

# Umbral para considerar un cliente como inactivo (14 minutos = 840 segundos)
INACTIVITY_THRESHOLD = 840

def download_authorized_ids():
    """Descarga authorized_ids.txt desde GitHub si no existe localmente."""
    if not os.path.exists(AUTHORIZED_FILE):
        try:
            headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
            response = requests.get(GITHUB_AUTHORIZED_IDS_URL, headers=headers)
            response.raise_for_status()
            with open(AUTHORIZED_FILE, 'w') as f:
                f.write(response.text)
            print(f"Descargado {AUTHORIZED_FILE} desde GitHub")
        except Exception as e:
            print(f"Error al descargar authorized_ids.txt: {e}")

def load_authorized_ids():
    authorized = {}
    download_authorized_ids()  # Descarga el archivo si no existe
    if os.path.exists(AUTHORIZED_FILE):
        with open(AUTHORIZED_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(',')
                if len(parts) == 3:
                    hardware_id, auth_date_str, days_valid = parts
                    try:
                        auth_date = datetime.strptime(auth_date_str, '%Y-%m-%d')
                        days_valid = int(days_valid)
                        expiration = auth_date + timedelta(days=days_valid)
                        authorized[hardware_id] = {"expiration": expiration}
                    except ValueError as e:
                        print(f"Formato inválido en línea: {line}, error: {e}")
    return authorized

def send_to_discord(message):
    """Envía un mensaje al webhook de Discord."""
    try:
        payload = {"content": message}
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        response.raise_for_status()
        print(f"Mensaje enviado a Discord: {message}")
    except Exception as e:
        print(f"Error al enviar mensaje a Discord: {e}")

@app.route('/submit_hardware_id', methods=['POST'])
def submit_hardware_id():
    data = request.get_json()
    hardware_id = data.get('hardware_id')
    instance_id = data.get('instance_id')
    if not hardware_id or not instance_id:
        return jsonify({"status": "error", "message": "Falta hardware_id o instance_id"}), 400
    
    # Enviar a Discord
    send_to_discord(f"Nuevo hardware_id registrado: {hardware_id}, instance_id: {instance_id}")
    
    # Registrar la actividad inicial del cliente
    if hardware_id not in client_activity:
        client_activity[hardware_id] = {"status": "active", "last_activity": time.time(), "instances": {}}
    client_activity[hardware_id]["instances"][instance_id] = time.time()
    client_activity[hardware_id]["status"] = "active"
    client_activity[hardware_id]["last_activity"] = time.time()
    
    return jsonify({"status": "success", "message": "hardware_id recibido"}), 200

@app.route('/verify', methods=['POST'])
def verify():
    data = request.get_json()
    hardware_id = data.get('hardware_id')
    instance_id = data.get('instance_id')
    if not hardware_id or not instance_id:
        return jsonify({"status": "error", "message": "Falta hardware_id o instance_id"}), 400
    
    authorized_ids = load_authorized_ids()
    current_date = datetime.now()
    
    if hardware_id in authorized_ids:
        expiration = authorized_ids[hardware_id]["expiration"]
        if current_date <= expiration:
            if hardware_id not in client_activity:
                client_activity[hardware_id] = {"status": "active", "last_activity": time.time(), "instances": {}, "expiration": expiration}
            client_activity[hardware_id]["instances"][instance_id] = time.time()
            client_activity[hardware_id]["status"] = "active"
            client_activity[hardware_id]["last_activity"] = time.time()
            return jsonify({
                "status": "success",
                "message": "Autorizado",
                "expiration": expiration.isoformat()  # Enviar la fecha de expiración
            }), 200
        else:
            return jsonify({"status": "error", "message": "Autorización expirada"}), 403
    else:
        return jsonify({"status": "error", "message": "No autorizado"}), 403

@app.route('/report_activity', methods=['POST'])
def report_activity():
    data = request.get_json()
    hardware_id = data.get('hardware_id')
    instance_id = data.get('instance_id')
    status = data.get('status')
    if not hardware_id or not instance_id or not status:
        return jsonify({"status": "error", "message": "Falta hardware_id, instance_id o status"}), 400
    
    authorized_ids = load_authorized_ids()
    current_date = datetime.now()
    
    if hardware_id in authorized_ids and current_date <= authorized_ids[hardware_id]["expiration"]:
        if hardware_id not in client_activity:
            client_activity[hardware_id] = {"status": "active", "last_activity": time.time(), "instances": {}, "expiration": authorized_ids[hardware_id]["expiration"]}
        
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
    else:
        return jsonify({"status": "error", "message": "No autorizado o autorización expirada"}), 403

@app.route('/get_hardware_ids', methods=['GET'])
def get_hardware_ids():
    authorized_ids = load_authorized_ids()
    current_date = datetime.now()
    valid_hardware_ids = [
        {"hardware_id": hid, "expiration": info["expiration"].isoformat()}
        for hid, info in authorized_ids.items()
        if current_date <= info["expiration"]
    ]
    return jsonify({"hardware_ids": valid_hardware_ids})

@app.route('/active_clients', methods=['GET'])
def active_clients():
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
    
    return jsonify({"clients": clients})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

from flask import Flask, request, jsonify
import time
import os

app = Flask(__name__)

# Archivo para almacenar hardware_ids autorizados
AUTHORIZED_FILE = "authorized_ids.txt"

# Diccionario para rastrear el estado de actividad e instancias
# Formato: {hardware_id: {"status": "active/inactive", "last_activity": timestamp, "instances": {instance_id: timestamp}}}
client_activity = {}

# Umbral para considerar un cliente como inactivo (16 minutos = 960 segundos)
INACTIVITY_THRESHOLD = 960

def load_authorized_ids():
    authorized = set()
    if os.path.exists(AUTHORIZED_FILE):
        with open(AUTHORIZED_FILE, 'r') as f:
            for line in f:
                hardware_id = line.strip()
                if hardware_id:
                    authorized.add(hardware_id)
    return authorized

def save_hardware_id(hardware_id):
    with open(AUTHORIZED_FILE, 'a') as f:
        f.write(hardware_id + '\n')

@app.route('/submit_hardware_id', methods=['POST'])
def submit_hardware_id():
    data = request.get_json()
    hardware_id = data.get('hardware_id')
    instance_id = data.get('instance_id')
    if not hardware_id or not instance_id:
        return jsonify({"status": "error", "message": "Falta hardware_id o instance_id"}), 400
    
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
    if hardware_id in authorized_ids:
        # Actualizar actividad
        if hardware_id not in client_activity:
            client_activity[hardware_id] = {"status": "active", "last_activity": time.time(), "instances": {}}
        client_activity[hardware_id]["instances"][instance_id] = time.time()
        client_activity[hardware_id]["status"] = "active"
        client_activity[hardware_id]["last_activity"] = time.time()
        return jsonify({"status": "success", "message": "Autorizado"}), 200
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
    
    if hardware_id not in client_activity:
        client_activity[hardware_id] = {"status": "active", "last_activity": time.time(), "instances": {}}
    
    if status == "active":
        client_activity[hardware_id]["instances"][instance_id] = time.time()
        client_activity[hardware_id]["status"] = "active"
        client_activity[hardware_id]["last_activity"] = time.time()
    elif status == "inactive":
        if instance_id in client_activity[hardware_id]["instances"]:
            del client_activity[hardware_id]["instances"][instance_id]
        # Si no hay más instancias, marcar como inactivo
        if not client_activity[hardware_id]["instances"]:
            client_activity[hardware_id]["status"] = "inactive"
    
    return jsonify({"status": "success", "message": "Actividad reportada"}), 200

@app.route('/active_clients', methods=['GET'])
def active_clients():
    current_time = time.time()
    clients = []
    for hardware_id, info in client_activity.items():
        # Verificar si el cliente está inactivo basado en el umbral
        if (current_time - info["last_activity"]) > INACTIVITY_THRESHOLD:
            info["status"] = "inactive"
            info["instances"] = {}  # Limpiar instancias si está inactivo
        
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
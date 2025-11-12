import os
from flask import Flask, jsonify, request, render_template_string
import datetime
import math
import pytz
from threading import Lock

# --- Konfigurasi Aplikasi ---
TOTAL_SLOTS = 5
HOURLY_RATE = 3000
TIMEZONE_STR = 'Asia/Jakarta'
TIMEZONE = pytz.timezone(TIMEZONE_STR)

# Inisialisasi Aplikasi Flask
app = Flask(__name__)

# --- Manajemen State (In-Memory) ---
# Gunakan Lock untuk menangani konkurensi (meskipun Flask dev server single-threaded, 
# ini adalah praktik yang baik untuk state global)
data_lock = Lock()

# 'active_tickets' adalah sumber kebenaran (source of truth)
# Format: { "T0001": {"ticket_id": "T0001", "plate_number": "B1234AA", "entry_time": datetime_obj, "slot_number": 1}, ... }
active_tickets = {}

# 'occupied_slots_count' digunakan untuk simulasi webhook.
# Dalam aplikasi nyata, kita akan selalu mengandalkan len(active_tickets),
# tapi kita ikuti spesifikasi untuk endpoint webhook.
# Kita akan jaga agar tetap sinkron.
occupied_slots_count = 0
next_ticket_number = 1

# --- Fungsi Helper ---

def get_current_time():
    """Mendapatkan waktu saat ini dalam zona waktu yang dikonfigurasi."""
    return datetime.datetime.now(TIMEZONE)

def generate_ticket_id():
    """Membuat ID tiket baru yang berurutan (T0001, T0002, ...)."""
    global next_ticket_number
    ticket_id = f"T{next_ticket_number:04d}"
    next_ticket_number += 1
    return ticket_id

def find_next_available_slot():
    """Mencari nomor slot parkir fisik pertama yang tersedia."""
    used_slots = {ticket['slot_number'] for ticket in active_tickets.values()}
    for i in range(1, TOTAL_SLOTS + 1):
        if i not in used_slots:
            return i
    return None

def calculate_cost(entry_time, exit_time):
    """
    Menghitung durasi dan biaya parkir.
    - Durasi dibulatkan ke atas ke jam terdekat.
    - Durasi minimum adalah 1 jam.
    """
    duration = exit_time - entry_time
    total_seconds = duration.total_seconds()
    
    # Bulatkan ke atas ke jam terdekat
    duration_hours = math.ceil(total_seconds / 3600)
    
    # Terapkan durasi minimum 1 jam
    if duration_hours < 1:
        duration_hours = 1
        
    cost = duration_hours * HOURLY_RATE
    return int(duration_hours), int(cost)

def format_datetime_str(dt_obj):
    """Memformat datetime object ke string yang rapi untuk UI."""
    if dt_obj:
        return dt_obj.strftime('%Y-%m-%d %H:%M:%S')
    return 'N/A'

# --- Inisialisasi Data Awal ---
def populate_initial_data():
    """Mengisi data awal saat aplikasi dimulai."""
    global occupied_slots_count
    
    # Kunci lock untuk memodifikasi state global
    with data_lock:
        if active_tickets: # Hanya jalankan sekali
            return

        print("Populating initial data...")
        
        initial_entries = [
            ("B1234AA", datetime.datetime(2025, 10, 17, 8, 0, 0)),
            ("D4567BB", datetime.datetime(2025, 10, 17, 9, 15, 0)),
            ("F7890CC", datetime.datetime(2025, 10, 17, 10, 30, 0))
        ]
        
        for plate, time in initial_entries:
            ticket_id = generate_ticket_id()
            slot = find_next_available_slot()
            if slot is None:
                print(f"Error: Could not find slot for initial data {plate}")
                continue
                
            active_tickets[ticket_id] = {
                "ticket_id": ticket_id,
                "plate_number": plate.upper(),
                "entry_time": TIMEZONE.localize(time), # Pastikan timezone-aware
                "slot_number": slot
            }
        
        # Sinkronkan counter (sesuai spesifikasi)
        occupied_slots_count = len(active_tickets)
        print(f"Initial data populated. Occupied slots: {occupied_slots_count}")


# --- ENDPOINT API ---

@app.route('/api/slots/available', methods=['GET'])
def get_available_slots():
    """Endpoint untuk mendapatkan status slot parkir saat ini."""
    with data_lock:
        # Gunakan counter 'occupied_slots_count' sesuai spesifikasi webhook
        available = TOTAL_SLOTS - occupied_slots_count
        
        return jsonify({
            "total_slots": TOTAL_SLOTS,
            "occupied_slots": occupied_slots_count,
            "available_slots": available if available >= 0 else 0
        })

@app.route('/api/entries', methods=['POST'])
def create_entry():
    """Endpoint untuk check-in mobil baru."""
    global occupied_slots_count
    
    data = request.get_json()
    if not data or 'plate_number' not in data or not data['plate_number'].strip():
        return jsonify({"error": "plate_number is required"}), 400

    plate_number = data['plate_number'].strip().upper()

    with data_lock:
        # 1. Cek ketersediaan berdasarkan counter (sesuai spek)
        if occupied_slots_count >= TOTAL_SLOTS:
            return jsonify({"error": "Parking lot is full"}), 400
            
        # 2. Cek slot fisik (cross-check dengan data tiket)
        slot_number = find_next_available_slot()
        if slot_number is None:
            # Ini terjadi jika counter tidak sinkron dengan active_tickets
            # Kita setel ulang counter dan kembalikan error
            occupied_slots_count = len(active_tickets)
            return jsonify({"error": "Parking lot is full (state desync detected)"}), 400

        # 3. Buat tiket baru
        entry_time = get_current_time()
        ticket_id = generate_ticket_id()
        
        new_ticket = {
            "ticket_id": ticket_id,
            "plate_number": plate_number,
            "slot_number": slot_number,
            "entry_time": entry_time
        }
        
        # 4. Simpan tiket dan update counter
        active_tickets[ticket_id] = new_ticket
        occupied_slots_count += 1
        
        # 5. Siapkan respons
        available_slots_now = TOTAL_SLOTS - occupied_slots_count
        
        return jsonify({
            "ticket_id": ticket_id,
            "plate_number": plate_number,
            "slot_number": slot_number,
            "entry_time": entry_time.isoformat(), # Format ISO 8601
            "available_slots": available_slots_now
        }), 201

@app.route('/api/exits', methods=['POST'])
def create_exit():
    """Endpoint untuk check-out mobil dan menghitung biaya."""
    global occupied_slots_count
    
    data = request.get_json()
    if not data or 'ticket_id' not in data:
        return jsonify({"error": "ticket_id is required"}), 400
        
    ticket_id = data['ticket_id'].strip().upper()
    
    with data_lock:
        # 1. Cari tiket
        ticket = active_tickets.get(ticket_id)
        if not ticket:
            return jsonify({"error": "Ticket not found"}), 404
            
        # 2. Hitung durasi dan biaya
        exit_time = get_current_time()
        entry_time = ticket['entry_time']
        duration_hours, cost = calculate_cost(entry_time, exit_time)
        
        # 3. Hapus tiket dari data aktif
        del active_tickets[ticket_id]
        
        # 4. Update counter (pastikan tidak negatif)
        if occupied_slots_count > 0:
            occupied_slots_count -= 1
        
        # 5. Kembalikan rincian biaya
        return jsonify({
            "ticket_id": ticket_id,
            "plate_number": ticket['plate_number'],
            "duration_hours": duration_hours,
            "cost": cost,
            "entry_time": entry_time.isoformat(),
            "exit_time": exit_time.isoformat()
        }), 200

@app.route('/api/tickets', methods=['GET'])
def get_all_tickets():
    """Endpoint helper untuk dashboard UI, mengambil semua tiket aktif."""
    with data_lock:
        now = get_current_time()
        tickets_list = []
        
        # Salin data untuk menghindari modifikasi saat iterasi
        current_tickets = list(active_tickets.values())
        
        for ticket in current_tickets:
            # Hitung biaya saat ini
            duration_hours, current_cost = calculate_cost(ticket['entry_time'], now)
            
            ticket_data = {
                "ticket_id": ticket['ticket_id'],
                "plate_number": ticket['plate_number'],
                "slot_number": ticket['slot_number'],
                "entry_time_str": format_datetime_str(ticket['entry_time']),
                "current_duration_hours": duration_hours,
                "current_cost": current_cost
            }
            tickets_list.append(ticket_data)

        # Urutkan berdasarkan nomor slot
        tickets_list.sort(key=lambda x: x['slot_number'])
        return jsonify(tickets_list)

# --- Endpoint Webhook (Sesuai Spesifikasi) ---

@app.route('/api/webhooks/slot-1', methods=['GET'])
def webhook_slot_minus():
    """Simulasi eksternal mengurangi counter slot terisi."""
    global occupied_slots_count
    with data_lock:
        if occupied_slots_count > 0:
            occupied_slots_count -= 1
        return jsonify({"message": "OK", "new_occupied_slots": occupied_slots_count})

@app.route('/api/webhooks/slot+1', methods=['GET'])
def webhook_slot_plus():
    """Simulasi eksternal menambah counter slot terisi."""
    global occupied_slots_count
    with data_lock:
        if occupied_slots_count < TOTAL_SLOTS:
            occupied_slots_count += 1
        return jsonify({"message": "OK", "new_occupied_slots": occupied_slots_count})

# --- Dashboard Web (UI) ---

# Simpan template HTML dalam sebuah variabel
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Parking Lot System</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #f4f7f6;
            color: #333;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 1000px;
            margin: 0 auto;
            background-color: #ffffff;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.05);
            padding: 20px;
        }
        h1, h2 {
            color: #1a535c;
            border-bottom: 2px solid #f0f0f0;
            padding-bottom: 10px;
        }
        h1 { text-align: center; }
        
        /* Layout Grid */
        .grid-layout {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
        }
        
        /* Kartu Status */
        .status-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-bottom: 20px;
        }
        .card {
            background-color: #f9f9f9;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }
        .card h3 {
            margin: 0 0 10px 0;
            color: #495057;
        }
        .card .value {
            font-size: 2.5rem;
            font-weight: bold;
        }
        #value-total { color: #4e8d7c; }
        #value-occupied { color: #f26419; }
        #value-available { color: #006400; }
        
        /* Form */
        .form-card {
            background-color: #fdfdfd;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 20px;
        }
        .form-card h2 { font-size: 1.25rem; }
        
        form { display: flex; flex-direction: column; }
        label { margin-bottom: 5px; font-weight: bold; }
        input[type="text"] {
            padding: 10px;
            border: 1px solid #ccc;
            border-radius: 4px;
            margin-bottom: 15px;
            font-size: 1rem;
        }
        button {
            padding: 12px;
            border: none;
            border-radius: 4px;
            background-color: #1a535c;
            color: white;
            font-size: 1rem;
            font-weight: bold;
            cursor: pointer;
            transition: background-color 0.2s;
        }
        button:hover { background-color: #4e8d7c; }
        
        /* Tabel Tiket */
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }
        th {
            background-color: #f2f2f2;
            color: #333;
        }
        tr:nth-child(even) { background-color: #f9f9f9; }
        
        /* Pesan Status */
        .message {
            margin-top: 15px;
            padding: 10px;
            border-radius: 4px;
            font-weight: bold;
            text-align: center;
        }
        .message.success { background-color: #d4edda; color: #155724; }
        .message.error { background-color: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Sistem Parkir</h1>
         <h2>Ghilman Arba</h2>
        
        <!-- Info Slot -->
        <h2>Status Slot</h2>
        <div class="status-grid">
            <div class="card">
                <h3>Total Slots</h3>
                <div class="value" id="value-total">...</div>
            </div>
            <div class="card">
                <h3>Occupied Slots</h3>
                <div class="value" id="value-occupied">...</div>
            </div>
            <div class="card">
                <h3>Available Slots</h3>
                <div class="value" id="value-available">...</div>
            </div>
        </div>
        
        <!-- Forms -->
        <div class="grid-layout">
            <!-- Form Check-in -->
            <div class="form-card">
                <h2>New Entry (Check-in)</h2>
                <form id="form-entry">
                    <label for="plate_number">Plate Number:</label>
                    <input type="text" id="plate_number" name="plate_number" placeholder="B 1234 CD" required>
                    <button type="submit">Check-in</button>
                </form>
                <div id="entry-message" class="message" style="display:none;"></div>
            </div>
            
            <!-- Form Check-out -->
            <div class="form-card">
                <h2>Settle Ticket (Check-out)</h2>
                <form id="form-exit">
                    <label for="ticket_id">Ticket ID:</label>
                    <input type="text" id="ticket_id" name="ticket_id" placeholder="T0001" required>
                    <button type="submit">Check-out</button>
                </form>
                <div id="exit-message" class="message" style="display:none;"></div>
            </div>
        </div>
        
        <!-- Daftar Tiket Aktif -->
        <h2>Active Tickets</h2>
        <table id="tickets-table">
            <thead>
                <tr>
                    <th>Ticket ID</th>
                    <th>Plate Number</th>
                    <th>Slot</th>
                    <th>Entry Time</th>
                    <th>Current Duration (H)</th>
                    <th>Current Cost (Rp)</th>
                </tr>
            </thead>
            <tbody id="tickets-tbody">
                <tr>
                    <td colspan="6" style="text-align:center;">Loading data...</td>
                </tr>
            </tbody>
        </table>
        
    </div>
    
    <script>
        // URL base API
        const API_URL = window.location.origin;
        
        // Elemen UI
        const valTotal = document.getElementById('value-total');
        const valOccupied = document.getElementById('value-occupied');
        const valAvailable = document.getElementById('value-available');
        const ticketsTbody = document.getElementById('tickets-tbody');
        const formEntry = document.getElementById('form-entry');
        const inputPlate = document.getElementById('plate_number');
        const msgEntry = document.getElementById('entry-message');
        const formExit = document.getElementById('form-exit');
        const inputTicket = document.getElementById('ticket_id');
        const msgExit = document.getElementById('exit-message');

        /**
         * Menampilkan pesan status di UI (untuk form)
         */
        function showMessage(element, type, text) {
            element.textContent = text;
            element.className = `message ${type}`;
            element.style.display = 'block';
            
            // Sembunyikan pesan setelah 5 detik
            setTimeout(() => {
                element.style.display = 'none';
            }, 5000);
        }

        /**
         * Memperbarui kartu status slot
         */
        async function updateSlotInfo() {
            try {
                const response = await fetch(`${API_URL}/api/slots/available`);
                if (!response.ok) throw new Error('Failed to fetch slot info');
                
                const data = await response.json();
                valTotal.textContent = data.total_slots;
                valOccupied.textContent = data.occupied_slots;
                valAvailable.textContent = data.available_slots;
                
                // Ubah warna jika penuh
                if (data.available_slots <= 0) {
                    valAvailable.style.color = '#dc3545'; // Merah
                } else {
                    valAvailable.style.color = '#006400'; // Hijau
                }
            } catch (error) {
                console.error("Error updating slot info:", error);
                valTotal.textContent = 'Err';
                valOccupied.textContent = 'Err';
                valAvailable.textContent = 'Err';
            }
        }
        
        /**
         * Memperbarui tabel tiket aktif
         */
        async function updateTicketsTable() {
            try {
                const response = await fetch(`${API_URL}/api/tickets`);
                if (!response.ok) throw new Error('Failed to fetch tickets');
                
                const tickets = await response.json();
                
                // Kosongkan tabel
                ticketsTbody.innerHTML = '';
                
                if (tickets.length === 0) {
                    ticketsTbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">No active tickets.</td></tr>';
                    return;
                }
                
                // Isi tabel dengan data baru
                tickets.forEach(ticket => {
                    const row = `
                        <tr>
                            <td>${ticket.ticket_id}</td>
                            <td>${ticket.plate_number}</td>
                            <td>${ticket.slot_number}</td>
                            <td>${ticket.entry_time_str}</td>
                            <td>${ticket.current_duration_hours}</td>
                            <td>${ticket.current_cost.toLocaleString('id-ID')}</td>
                        </tr>
                    `;
                    ticketsTbody.innerHTML += row;
                });
                
            } catch (error) {
                console.error("Error updating tickets table:", error);
                ticketsTbody.innerHTML = '<tr><td colspan="6" style="text-align:center;">Error loading data.</td></tr>';
            }
        }
        
        /**
         * Fungsi utama untuk me-refresh seluruh dashboard
         */
        function updateDashboard() {
            updateSlotInfo();
            updateTicketsTable();
        }

        /**
         * Menangani submit form check-in
         */
        formEntry.addEventListener('submit', async (e) => {
            e.preventDefault();
            const plateNumber = inputPlate.value;
            if (!plateNumber) return;
            
            try {
                const response = await fetch(`${API_URL}/api/entries`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ plate_number: plateNumber })
                });
                
                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.error || 'Failed to check-in');
                }
                
                // Sukses
                showMessage(msgEntry, 'success', `Success! Ticket ${data.ticket_id} created for slot ${data.slot_number}.`);
                inputPlate.value = ''; // Kosongkan input
                updateDashboard(); // Refresh data
                
            } catch (error) {
                console.error("Entry error:", error);
                showMessage(msgEntry, 'error', `Error: ${error.message}`);
            }
        });
        
        /**
         * Menangani submit form check-out
         */
        formExit.addEventListener('submit', async (e) => {
            e.preventDefault();
            const ticketId = inputTicket.value;
            if (!ticketId) return;
            
            try {
                const response = await fetch(`${API_URL}/api/exits`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ticket_id: ticketId })
                });
                
                const data = await response.json();
                
                if (!response.ok) {
                    throw new Error(data.error || 'Failed to check-out');
                }
                
                // Sukses
                const costFormatted = data.cost.toLocaleString('id-ID');
                const msg = `Success! Ticket ${data.ticket_id} (${data.plate_number}) checked out. Duration: ${data.duration_hours}h. Cost: Rp ${costFormatted}`;
                showMessage(msgExit, 'success', msg);
                inputTicket.value = ''; // Kosongkan input
                updateDashboard(); // Refresh data
                
            } catch (error) {
                console.error("Exit error:", error);
                showMessage(msgExit, 'error', `Error: ${error.message}`);
            }
        });
        
        // --- Inisialisasi Saat Halaman Dimuat ---
        document.addEventListener('DOMContentLoaded', () => {
            console.log("Parking System UI Initialized");
            updateDashboard();
            
            // Auto-refresh setiap 30 detik untuk memperbarui biaya saat ini
            setInterval(updateDashboard, 30000);
        });
        
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Menyajikan dashboard web utama."""
    # Render template HTML yang disimpan di variabel
    return render_template_string(HTML_TEMPLATE)


# --- Main Runner ---
if __name__ == '__main__':
    # Pastikan data awal dimuat sebelum aplikasi mulai menerima request
    with app.app_context():
        populate_initial_data()
        
    # Jalankan aplikasi
    # Gunakan host='0.0.0.0' agar bisa diakses dari jaringan lokal
    app.run(host='0.0.0.0', port=5000, debug=True)

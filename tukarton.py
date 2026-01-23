import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from datetime import datetime
import asyncio
import aiohttp
import sqlite3
import json

TELEGRAM_BOT_TOKEN = "8441818839:AAHlk5SpCY71yNj9oHHzGey-cXIjDrdl-QY"

MARGIN_PER_TON = 1000
MIN_TON = 0.5
MAX_TRANSACTION_IDR = 1000000  # Maksimal Rp. 1.000.000 per transaksi

ADMIN_USERNAME = "insikeX"
OWNER_USER_ID = 6683929810 

YOUR_TON_WALLET = "UQCWSP7k-g_fbPrttnwV3Aahfmt5bpmXZS5bkgR2CPWqVluE"

TESTIMONI_CHANNEL = "tukartontips"  # Username channel tanpa @ untuk link testimoni

# ============================================================
# START OF REFERRAL SYSTEM CONFIGURATION
# ============================================================
REFERRAL_PERCENTAGE = 0.3  # 0.3% dari setiap transaksi referral
MIN_WITHDRAWAL_AMOUNT = 25000  # Minimal Rp 25.000 untuk penarikan
# ============================================================
# END OF REFERRAL SYSTEM CONFIGURATION
# ============================================================

PAYMENT_METHODS = {
    'bank': {
        'name': 'Transfer Bank',
        'options': {
            'BCA': {'fee': 2500},
            'BRI': {'fee': 2500},
            'BNI': {'fee': 2500},
            'MANDIRI': {'fee': 2500},
            'SEABANK': {'fee': 0}
        }
    },
    'ewallet': {
        'name': 'E-Wallet',
        'fee': 1200,
        'options': ['DANA', 'GOPAY', 'OVO', 'SHOPEEPAY']
    }
}

COPYRIGHT_TEXT = "\n\n<i>© 2026 Vyérru & Co.</i>"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DB_FILE = 'tonbot_data.db'

def init_database():
    """Inisialisasi database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            payment_method_type TEXT,
            payment_method TEXT,
            account_name TEXT,
            account_number TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            ton_amount REAL NOT NULL,
            price_per_ton REAL NOT NULL,
            fee REAL NOT NULL,
            total REAL NOT NULL,
            payment_method_type TEXT,
            payment_method TEXT,
            account_name TEXT,
            account_number TEXT,
            memo TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # ============================================================
    # START OF REFERRAL SYSTEM DATABASE TABLES
    # ============================================================
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referrer_id) REFERENCES users (user_id),
            FOREIGN KEY (referred_id) REFERENCES users (user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referral_earnings (
            user_id INTEGER PRIMARY KEY,
            referral_balance REAL DEFAULT 0,
            total_referrals INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdrawal_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_method TEXT,
            account_name TEXT,
            account_number TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    # ============================================================
    # END OF REFERRAL SYSTEM DATABASE TABLES
    # ============================================================
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

def save_user(user_id, username=None, first_name=None, payment_info=None):
    """Simpan atau update data user"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    if payment_info:
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, payment_method_type, 
                             payment_method, account_name, account_number, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                payment_method_type = excluded.payment_method_type,
                payment_method = excluded.payment_method,
                account_name = excluded.account_name,
                account_number = excluded.account_number,
                updated_at = CURRENT_TIMESTAMP
        ''', (user_id, username, first_name, 
              payment_info.get('payment_method_type'),
              payment_info.get('payment_method'),
              payment_info.get('account_name'),
              payment_info.get('account_number')))
    else:
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                updated_at = CURRENT_TIMESTAMP
        ''', (user_id, username, first_name))
    
    conn.commit()
    conn.close()

def get_user(user_id):
    """Ambil data user dari database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, username, first_name, payment_method_type, 
               payment_method, account_name, account_number, created_at
        FROM users WHERE user_id = ?
    ''', (user_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'user_id': row[0],
            'username': row[1],
            'first_name': row[2],
            'payment_method_type': row[3],
            'payment_method': row[4],
            'account_name': row[5],
            'account_number': row[6],
            'created_at': row[7]
        }
    return None

def save_transaction(order_data, user_id, username, first_name):
    """Simpan transaksi ke database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO transactions (
            order_id, user_id, ton_amount, price_per_ton, fee, total,
            payment_method_type, payment_method, account_name, account_number,
            memo, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
    ''', (
        order_data['order_id'],
        user_id,
        order_data['ton_amount'],
        order_data['price_per_ton'],
        order_data['fee'],
        order_data['total'],
        order_data['payment_method_type'],
        order_data['payment_method'],
        order_data['account_name'],
        order_data['account_number'],
        order_data.get('memo', '')
    ))
    
    conn.commit()
    conn.close()

def get_transaction(order_id):
    """Ambil data transaksi"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT t.*, u.username, u.first_name
        FROM transactions t
        JOIN users u ON t.user_id = u.user_id
        WHERE t.order_id = ?
    ''', (order_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'order_id': row[1],
            'user_id': row[2],
            'ton_amount': row[3],
            'price_per_ton': row[4],
            'fee': row[5],
            'total': row[6],
            'payment_method_type': row[7],
            'payment_method': row[8],
            'account_name': row[9],
            'account_number': row[10],
            'memo': row[11],
            'status': row[12],
            'username': row[15],
            'first_name': row[16]
        }
    return None

def get_user_transactions(user_id, limit=100):
    """Ambil riwayat transaksi user"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT order_id, ton_amount, price_per_ton, total, status, 
               created_at, completed_at, payment_method
        FROM transactions 
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    ''', (user_id, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    transactions = []
    for row in rows:
        transactions.append({
            'order_id': row[0],
            'ton_amount': row[1],
            'price_per_ton': row[2],
            'total': row[3],
            'status': row[4],
            'created_at': row[5],
            'completed_at': row[6],
            'payment_method': row[7]
        })
    
    return transactions

def get_user_stats(user_id):
    """Ambil statistik transaksi user"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM transactions WHERE user_id = ?', (user_id,))
    total_trans = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ? AND status = 'completed'", (user_id,))
    completed_trans = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ? AND status = 'pending'", (user_id,))
    pending_trans = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(ton_amount) FROM transactions WHERE user_id = ? AND status = 'completed'", (user_id,))
    total_ton = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT SUM(total) FROM transactions WHERE user_id = ? AND status = 'completed'", (user_id,))
    total_idr = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return {
        'total_transactions': total_trans,
        'completed_transactions': completed_trans,
        'pending_transactions': pending_trans,
        'total_ton_sold': total_ton,
        'total_idr_received': total_idr
    }

def complete_transaction(order_id):
    """Tandai transaksi sebagai selesai"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE transactions 
        SET status = 'completed', completed_at = CURRENT_TIMESTAMP
        WHERE order_id = ?
    ''', (order_id,))
    
    conn.commit()
    conn.close()
    
    # ============================================================
    # START OF REFERRAL SYSTEM - PROCESS REFERRAL EARNING
    # ============================================================
    # Proses penghasilan referral setelah transaksi selesai
    transaction = get_transaction(order_id)
    if transaction:
        user_id = transaction['user_id']
        total_amount = transaction['total']
        process_referral_earning(user_id, total_amount)
    # ============================================================
    # END OF REFERRAL SYSTEM - PROCESS REFERRAL EARNING
    # ============================================================

def get_statistics():
    """Ambil statistik dari database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE status = 'completed'")
    completed_transactions = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM transactions WHERE status = 'pending'")
    pending_transactions = cursor.fetchone()[0]
    
    conn.close()
    
    return {
        'total_users': total_users,
        'completed_transactions': completed_transactions,
        'pending_transactions': pending_transactions
    }

# ============================================================
# START OF REFERRAL SYSTEM DATABASE FUNCTIONS
# ============================================================
def save_referral(referrer_id: int, referred_id: int) -> bool:
    """Simpan hubungan referral ke database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # Cek apakah referred_id sudah pernah direferensikan
        cursor.execute('SELECT id FROM referrals WHERE referred_id = ?', (referred_id,))
        if cursor.fetchone():
            conn.close()
            return False  # Sudah pernah direferensikan
        
        # Cek apakah referrer_id sama dengan referred_id
        if referrer_id == referred_id:
            conn.close()
            return False
        
        # Simpan referral
        cursor.execute('''
            INSERT INTO referrals (referrer_id, referred_id)
            VALUES (?, ?)
        ''', (referrer_id, referred_id))
        
        # Update atau buat record referral_earnings untuk referrer
        cursor.execute('''
            INSERT INTO referral_earnings (user_id, total_referrals)
            VALUES (?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                total_referrals = total_referrals + 1,
                updated_at = CURRENT_TIMESTAMP
        ''', (referrer_id,))
        
        conn.commit()
        conn.close()
        logger.info(f"Referral saved: {referrer_id} referred {referred_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving referral: {e}")
        conn.close()
        return False

def get_referrer(referred_id: int) -> int:
    """Dapatkan user_id dari referrer berdasarkan referred_id"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT referrer_id FROM referrals WHERE referred_id = ?', (referred_id,))
    row = cursor.fetchone()
    conn.close()
    
    return row[0] if row else None

def add_referral_earning(referrer_id: int, amount: float) -> bool:
    """Tambahkan penghasilan referral ke saldo referrer"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO referral_earnings (user_id, referral_balance)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                referral_balance = referral_balance + ?,
                updated_at = CURRENT_TIMESTAMP
        ''', (referrer_id, amount, amount))
        
        conn.commit()
        conn.close()
        logger.info(f"Added referral earning: {amount} to user {referrer_id}")
        return True
    except Exception as e:
        logger.error(f"Error adding referral earning: {e}")
        conn.close()
        return False

def get_referral_stats(user_id: int) -> dict:
    """Dapatkan statistik referral untuk user"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT referral_balance, total_referrals
        FROM referral_earnings
        WHERE user_id = ?
    ''', (user_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'referral_balance': row[0] or 0,
            'total_referrals': row[1] or 0
        }
    return {
        'referral_balance': 0,
        'total_referrals': 0
    }

def process_referral_earning(transaction_user_id: int, transaction_amount: float) -> bool:
    """Proses penghasilan referral saat transaksi selesai"""
    referrer_id = get_referrer(transaction_user_id)
    
    if referrer_id:
        # Hitung 0.3% dari transaksi
        referral_earning = transaction_amount * (REFERRAL_PERCENTAGE / 100)
        return add_referral_earning(referrer_id, referral_earning)
    
    return False

def deduct_referral_balance(user_id: int, amount: float) -> bool:
    """Kurangi saldo referral setelah penarikan"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE referral_earnings
            SET referral_balance = referral_balance - ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND referral_balance >= ?
        ''', (amount, user_id, amount))
        
        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            return True
        else:
            conn.close()
            return False
    except Exception as e:
        logger.error(f"Error deducting referral balance: {e}")
        conn.close()
        return False

def save_withdrawal_request(user_id: int, amount: float, payment_method: str, 
                           account_name: str, account_number: str) -> int:
    """Simpan permintaan penarikan"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO withdrawal_requests 
            (user_id, amount, payment_method, account_name, account_number)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, amount, payment_method, account_name, account_number))
        
        request_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return request_id
    except Exception as e:
        logger.error(f"Error saving withdrawal request: {e}")
        conn.close()
        return None

def get_withdrawal_request(request_id: int) -> dict:
    """Ambil data permintaan penarikan berdasarkan ID"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT wr.id, wr.user_id, wr.amount, wr.payment_method, 
                   wr.account_name, wr.account_number, wr.status, wr.created_at,
                   u.username, u.first_name
            FROM withdrawal_requests wr
            JOIN users u ON wr.user_id = u.user_id
            WHERE wr.id = ?
        ''', (request_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'id': row[0],
                'user_id': row[1],
                'amount': row[2],
                'payment_method': row[3],
                'account_name': row[4],
                'account_number': row[5],
                'status': row[6],
                'created_at': row[7],
                'username': row[8],
                'first_name': row[9]
            }
        return None
    except Exception as e:
        logger.error(f"Error getting withdrawal request: {e}")
        conn.close()
        return None

def complete_withdrawal_request(request_id: int) -> bool:
    """Tandai permintaan penarikan sebagai selesai"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE withdrawal_requests 
            SET status = 'completed', processed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (request_id,))
        
        if cursor.rowcount > 0:
            conn.commit()
            conn.close()
            logger.info(f"Withdrawal request {request_id} marked as completed")
            return True
        else:
            conn.close()
            return False
    except Exception as e:
        logger.error(f"Error completing withdrawal request: {e}")
        conn.close()
        return False
# ============================================================
# END OF REFERRAL SYSTEM DATABASE FUNCTIONS
# ============================================================

# ============================================================
# START OF BROADCAST SYSTEM DATABASE FUNCTIONS
# ============================================================
def get_all_user_ids() -> list:
    """Ambil semua user_id dari database untuk broadcast"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT user_id FROM users')
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"Error getting all user ids: {e}")
        conn.close()
        return []

def save_broadcast_log(admin_id: int, message: str, total_users: int, success_count: int, failed_count: int) -> int:
    """Simpan log broadcast ke database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # Buat tabel jika belum ada
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS broadcast_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                message TEXT,
                total_users INTEGER,
                success_count INTEGER,
                failed_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            INSERT INTO broadcast_logs (admin_id, message, total_users, success_count, failed_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (admin_id, message[:500], total_users, success_count, failed_count))  # Simpan 500 karakter pertama
        
        log_id = cursor.lastrowid
        conn.commit()
        conn.close()
        logger.info(f"Broadcast log saved: ID {log_id}, sent to {success_count}/{total_users} users")
        return log_id
    except Exception as e:
        logger.error(f"Error saving broadcast log: {e}")
        conn.close()
        return None
# ============================================================
# END OF BROADCAST SYSTEM DATABASE FUNCTIONS
# ============================================================

def calculate_max_ton(price_per_ton, payment_method_type, payment_method):
    """Hitung maksimal TON berdasarkan batas Rp. 1.000.000"""
    fee = get_payment_fee(payment_method_type, payment_method)
    max_ton = (MAX_TRANSACTION_IDR + fee) / price_per_ton
    return round(max_ton, 2)

pending_orders = {} 
user_payment_info = {} 
notification_messages = {}  # Menyimpan message_id notifikasi untuk setiap order_id 

ton_price_cache = {
    'price_idr': 0,
    'price_usd': 0,
    'last_update': None
}

TEXTS = {
    'welcome': "Selamat datang {user_greeting} di @tukartonbot\n\nJual TON 💎 Anda dan Terima Rupiah dengan Cepat dan Aman\n\nGunakan menu button di bawah untuk memulai." + COPYRIGHT_TEXT,
    
    'setup_payment_required': "⚠️ <b>Atur Metode Pembayaran</b>\n\n<i>Sebelum menjual TON, silakan atur metode pembayaran terlebih dahulu.</i>" + COPYRIGHT_TEXT,
    
    'select_payment_method': "💳 <b>Pilih Metode Pembayaran</b>\n\n<i>Pilih metode pembayaran untuk menerima dana:</i>",
    
    'select_bank': "🏦 <b>Pilih Bank</b>\n\n<i>Biaya admin:</i>\n• BCA, BRI, BNI, Mandiri: Rp 2.500\n• SeaBank: <b>Gratis</b>",
    
    'select_ewallet': "📱 <b>Pilih E-Wallet</b>\n\n<i>Biaya admin: Rp 1.200</i>",
    
    'input_account_name': "💳 <b>Metode:</b> {method}\n\n<i>Masukkan nama pemilik rekening:</i>\nContoh: Budi Santoso",
    
    'input_account_number': "💳 <b>Metode:</b> {method}\n👤 <b>Nama:</b> {name}\n\n<i>Masukkan nomor rekening:</i>\nContoh: 1234567890",
    
    'payment_method_saved': "✅ <b>Metode Pembayaran Tersimpan</b>\n\n💳 <b>Metode:</b> {method}\n👤 <b>Nama:</b> {name}\n🔢 <b>Nomor:</b> <code>{number}</code>\n\n<i>Sekarang Anda dapat menjual TON.</i>" + COPYRIGHT_TEXT,
    
    'input_ton_amount': "💎 <b>Jual Toncoin</b>\n\n💰 <b>Harga beli:</b> Rp {price:,.0f}/TON\n📊 <b>Minimum:</b> {min_ton} TON\n🔴 <b>Maksimal:</b> {max_ton} TON (≈ Rp {max_idr:,.0f})\n\n<i>Masukkan jumlah TON:</i>",
    
    'send_ton_instruction': "📋 <b>Detail Transaksi</b>\n\n💎 <b>Jumlah TON:</b> {ton_amount}\n💰 <b>Harga:</b> Rp {price_per_ton:,.0f}/TON\n📊 <b>Biaya admin:</b> Rp {fee:,.0f}\n─────────────\n💵 <b>Total diterima:</b> Rp {total:,.0f}\n\n<b>📤 Alamat Tujuan:</b>\n<code>{wallet}</code>\n\n⚠️ <b>PENTING - MEMO OTOMATIS:</b>\n<code>{memo}</code>\n\n💡 <b>Cara Bayar:</b>\n️ • Klik tombol <b>💎 Bayar Sekarang</b>\n • Aplikasi TON Wallet akan terbuka otomatis\n • Memo/Comment sudah terisi otomatis: <code>{memo}</code>\n • Periksa jumlah TON: <b>{ton_amount}</b>\n • Konfirmasi pembayaran\n • Klik <b>✅ Sudah Kirim</b> dan upload bukti\n\n⚠️ <b>Catatan Penting:</b>\n• Jangan ubah memo/comment\n• Jangan kirim dari exchange\n• Pastikan jaringan TON\n• Tanpa memo = transfer ditolak!",
    
    'waiting_payment_proof': "📸 <b>Kirim Bukti Transfer</b>\n\n<i>Upload screenshot yang menampilkan:</i>\n• Jumlah TON\n• Alamat tujuan\n• <b>Komentar/Memo: {memo}</b>\n• Status berhasil\n\n⚠️ <b>Pastikan komentar terlihat di screenshot!</b>\n\n⏳ <i>Menunggu bukti transfer...</i>",
    
    'proof_received': "✅ <b>Bukti Diterima</b>\n\n💎 <b>TON:</b> {ton_amount}\n💰 <b>Anda terima:</b> Rp {total:,.0f}\n💳 <b>Metode:</b> {payment_method}\n\n🆔 <b>Kode:</b> <code>{order_id}</code>\n\n⏰ <i>Mohon tunggu, admin akan memproses pembayaran Anda.</i>" + COPYRIGHT_TEXT,
    
    'order_cancelled': "❌ <i>Transaksi dibatalkan</i>" + COPYRIGHT_TEXT,
    
    'invalid_number': "❌ <i>Mohon masukkan angka yang valid</i>\n\nContoh: 5",
    
    'invalid_amount': "❌ <i>Jumlah minimum {min_ton} TON</i>",
    
    'invalid_max_amount': "❌ <i>Maksimal {max_ton} TON (≈ Rp {max_idr:,.0f})</i>\n\n💡 <i>Batas maksimal transaksi: Rp 1.000.000</i>",
    
    'help_text': "ℹ️ <b>Informasi Bot</b>\n\n💰 <b>Harga Jual TON:</b> Rp {price:,.0f}/TON\n🔴 <b>Maksimal Transaksi:</b> Rp 1.000.000\n─────────────\n💳 <b>Tersedia Metode pembayaran:</b>\n• BCA\n• BRI\n• BNI\n• Mandiri\n• SeaBank\n• Dana\n• GoPay\n• OVO\n• ShopeePay\n─────────────\n📝 <b>Cara jual TON:</b>\n1. Atur metode pembayaran\n2. Klik Jual TON\n3. Masukkan jumlah\n4. Kirim TON ke wallet\n5. Upload bukti\n6. Terima Rupiah" + COPYRIGHT_TEXT,
    
    'admin_notification': "🔔 <b>TRANSAKSI BARU!</b>\n\n👤 <b>Penjual:</b>\n{user_info}\n🆔 <b>ID:</b> <code>{user_id}</code>\n\n💎 <b>Detail Transaksi:</b>\n💎 <b>Jumlah TON:</b> {ton_amount}\n💬 <b>Memo/Comment:</b> <code>{memo}</code>\n💰 <b>Transfer ke user:</b> Rp {total:,.0f}\n\n💳 <b>Kirim ke:</b>\n{payment_info}\n\n📸 <b>Bukti Transfer TON:</b>\n<i>(Lihat foto di bawah)</i>\n\n🆔 <b>Kode:</b> <code>{order_id}</code>\n\n<b>Untuk konfirmasi setelah transfer:</b>\n<code>selesai {order_id}</code>",
    
    'admin_confirm_success': "✅ <b>Konfirmasi Berhasil</b>\n\n<i>Notifikasi terkirim ke:</i>\n{user_mention}\n💰 Transfer: Rp {total:,.0f}",
    
    'user_payment_received': "✅ <b>Pembayaran Diterima!</b>\n\n💰 Transfer <b>Rp {total:,.0f}</b> telah masuk ke rekening Anda dari penjualan <b>{ton_amount} TON</b>.\n\n✨ <i>Terima kasih telah menggunakan layanan kami.</i>\n\n📢 Berikan testimoni: https://t.me/{channel}" + COPYRIGHT_TEXT,
    
    'admin_only': "⚠️ <i>Fitur ini hanya untuk admin</i>",
    
    'invalid_format': "❌ <b>Format salah</b>\n\n<i>Gunakan:</i> <code>selesai ORD-12345678</code>",
    
    'order_not_found': "❌ <i>Kode transaksi tidak ditemukan</i>",
    
    'owner_only': "⚠️ <i>Fitur ini hanya untuk pemilik</i>",
    
    'stats_menu': "📊 <b>Statistik Bot</b>\n\n👥 <b>Total pengguna:</b> {total_users}\n💰 <b>Harga TON:</b> Rp {price:,.0f}\n✅ <b>Transaksi selesai:</b> {completed_trans}\n⏳ <b>Transaksi pending:</b> {pending_trans}\n\n<i>Diperbarui: {update_time}</i>",
    
    'public_stats': "📊 <b>Statistik</b>\n\n👥 <b>Pengguna:</b> {total_users}\n💰 <b>Harga:</b> Rp {price:,.0f}/TON\n✅ <b>Transaksi:</b> {completed_trans}\n\n<i>Diperbarui: {update_time}</i>" + COPYRIGHT_TEXT,
    
    'confirm_payment_info': "✅ <b>Konfirmasi Data Pembayaran</b>\n\n💳 <b>Metode:</b> {method}\n👤 <b>Nama:</b> {name}\n🔢 <b>Nomor:</b> <code>{number}</code>\n\n<i>Apakah data sudah benar?</i>",
    
    'price_update_failed': "⚠️ <i>Gagal mengambil harga TON. Coba lagi nanti.</i>",
    
    'please_send_text': "❌ <i>Mohon kirim pesan teks, bukan {type}</i>",
    
    'please_send_photo': "❌ <i>Mohon kirim foto bukti transfer</i>",
    
    'no_transactions': "📜 <b>Riwayat Transaksi</b>\n\n<i>Anda belum memiliki transaksi.</i>" + COPYRIGHT_TEXT,
    
    # ============================================================
    # START OF REFERRAL SYSTEM TEXTS
    # ============================================================
    'referral_balance': "💰 <b>Saldo Rujukan Anda</b>\n\n💵 <b>Total Penghasilan:</b> Rp {balance:,.0f}\n👥 <b>Jumlah Rujukan Sukses:</b> {total_referrals} orang\n\n🔗 <b>Link Rujukan Anda:</b>\n<code>https://t.me/{bot_username}?start=ref_{user_id}</code>\n\n💡 <i>Bagikan link di atas dan dapatkan 0.3% dari setiap transaksi orang yang bergabung melalui link Anda!</i>" + COPYRIGHT_TEXT,
    
    'referral_welcome': "🎉 <b>Selamat!</b>\n\nAnda bergabung melalui rujukan dari pengguna lain. Selamat menggunakan layanan kami!" + COPYRIGHT_TEXT,
    
    'referral_new_user': "🎊 <b>Rujukan Baru!</b>\n\n👤 <b>{referred_name}</b> bergabung melalui link rujukan Anda!\n\n💡 <i>Anda akan mendapat 0.3% dari setiap transaksi mereka.</i>",
    
    'referral_earning_notification': "💰 <b>Penghasilan Rujukan!</b>\n\n💵 <b>+Rp {amount:,.0f}</b>\n\nAnda mendapat komisi dari transaksi rujukan Anda.\n\n📊 <b>Saldo rujukan saat ini:</b> Rp {new_balance:,.0f}",
    
    'withdrawal_request_sent': "✅ <b>Permintaan Penarikan Terkirim</b>\n\n💵 <b>Jumlah:</b> Rp {amount:,.0f}\n💳 <b>Metode:</b> {payment_method}\n👤 <b>Nama:</b> {account_name}\n🔢 <b>Nomor:</b> <code>{account_number}</code>\n\n⏳ <i>Mohon tunggu, admin akan memproses penarikan Anda.</i>" + COPYRIGHT_TEXT,
    
    'withdrawal_insufficient': "❌ <b>Saldo Tidak Cukup</b>\n\n💵 <b>Saldo Anda:</b> Rp {balance:,.0f}\n📊 <b>Minimal Penarikan:</b> Rp {min_amount:,.0f}\n\n<i>Kumpulkan lebih banyak rujukan untuk mencapai batas minimal penarikan!</i>" + COPYRIGHT_TEXT,
    
    'withdrawal_confirm': "💳 <b>Konfirmasi Penarikan</b>\n\n💵 <b>Jumlah:</b> Rp {amount:,.0f}\n💳 <b>Metode:</b> {payment_method}\n👤 <b>Nama:</b> {account_name}\n🔢 <b>Nomor:</b> <code>{account_number}</code>\n\n<i>Apakah data sudah benar?</i>",
    
    'withdrawal_admin_notification': "🔔 <b>PERMINTAAN PENARIKAN!</b>\n\n👤 <b>User:</b> {user_info}\n🆔 <b>ID:</b> <code>{user_id}</code>\n\n💵 <b>Jumlah:</b> Rp {amount:,.0f}\n💳 <b>Metode:</b> {payment_method}\n👤 <b>Nama:</b> {account_name}\n🔢 <b>Nomor:</b> <code>{account_number}</code>\n\n🆔 <b>Request ID:</b> <code>WD-{request_id}</code>\n\n<b>Untuk konfirmasi setelah transfer:</b>\n<code>bayarwd WD-{request_id}</code>",
    
    'no_payment_method_withdrawal': "⚠️ <b>Metode Pembayaran Belum Diatur</b>\n\n<i>Silakan atur metode pembayaran terlebih dahulu sebelum melakukan penarikan.</i>" + COPYRIGHT_TEXT,
    
    'withdrawal_completed': "✅ <b>Penarikan Berhasil!</b>\n\n💵 <b>Jumlah:</b> Rp {amount:,.0f}\n💳 <b>Metode:</b> {payment_method}\n👤 <b>Nama:</b> {account_name}\n🔢 <b>Nomor:</b> <code>{account_number}</code>\n\n✨ <i>Dana telah ditransfer ke rekening Anda.</i>" + COPYRIGHT_TEXT,
    
    'admin_withdrawal_confirm_success': "✅ <b>Penarikan Dikonfirmasi</b>\n\n<i>Notifikasi terkirim ke:</i>\n{user_mention}\n💰 Transfer: Rp {amount:,.0f}",
    
    'withdrawal_not_found': "❌ <i>Permintaan penarikan tidak ditemukan</i>",
    
    'withdrawal_invalid_format': "❌ <b>Format salah</b>\n\n<i>Gunakan:</i> <code>bayarwd WD-12345</code>",
    # ============================================================
    # END OF REFERRAL SYSTEM TEXTS
    # ============================================================
    
    # ============================================================
    # START OF BROADCAST SYSTEM TEXTS
    # ============================================================
    'broadcast_admin_only': "⚠️ <i>Perintah /broadcast hanya untuk admin.</i>",
    
    'broadcast_usage': "📢 <b>Cara Penggunaan Broadcast</b>\n\n"
                       "<b>Format:</b>\n"
                       "<code>/broadcast [pesan]</code>\n\n"
                       "<b>Contoh:</b>\n"
                       "<code>/broadcast 🎉 Update Baru! Sekarang ada fitur referral!</code>\n\n"
                       "<b>Untuk broadcast dengan gambar:</b>\n"
                       "1. Kirim gambar dengan caption yang diawali <code>/broadcast</code>\n"
                       "2. Contoh caption: <code>/broadcast 🔥 Promo Spesial!</code>\n\n"
                       "💡 <i>Pesan akan dikirim ke semua pengguna bot.</i>",
    
    'broadcast_started': "📢 <b>Broadcast Dimulai</b>\n\n"
                         "📝 <b>Pesan:</b>\n{message}\n\n"
                         "👥 <b>Total User:</b> {total_users}\n"
                         "⏳ <i>Sedang mengirim...</i>",
    
    'broadcast_completed': "✅ <b>Broadcast Selesai</b>\n\n"
                           "📝 <b>Pesan:</b>\n{message}\n\n"
                           "📊 <b>Hasil:</b>\n"
                           "👥 Total User: {total_users}\n"
                           "✅ Berhasil: {success_count}\n"
                           "❌ Gagal: {failed_count}\n\n"
                           "⏱️ <i>Waktu: {duration:.1f} detik</i>",
    
    'broadcast_no_users': "⚠️ <i>Tidak ada pengguna untuk broadcast.</i>",
    
    'broadcast_confirm': "📢 <b>Konfirmasi Broadcast</b>\n\n"
                         "📝 <b>Pesan yang akan dikirim:</b>\n"
                         "────────────────\n"
                         "{message}\n"
                         "────────────────\n\n"
                         "👥 <b>Akan dikirim ke:</b> {total_users} pengguna\n\n"
                         "⚠️ <i>Apakah Anda yakin ingin mengirim broadcast ini?</i>",
    
    'broadcast_cancelled': "❌ <i>Broadcast dibatalkan.</i>",
    
    'broadcast_with_image': "📢 <b>Broadcast dengan Gambar</b>\n\n"
                            "📝 <b>Caption:</b>\n{message}\n\n"
                            "👥 <b>Total User:</b> {total_users}\n"
                            "⏳ <i>Sedang mengirim...</i>",
    # ============================================================
    # END OF BROADCAST SYSTEM TEXTS
    # ============================================================
}

def get_text(key: str, **kwargs) -> str:
    """Ambil teks dengan format"""
    text = TEXTS.get(key, "")
    return text.format(**kwargs) if kwargs else text

def get_main_button_keyboard():
    """Buat keyboard tombol menu utama"""
    keyboard = [
        [KeyboardButton("💎 Jual TON")],
        [KeyboardButton("📜 Riwayat"), KeyboardButton("💰 Saldo")],  # Tambah tombol Saldo
        [KeyboardButton("💳 Atur Pembayaran")],
        [KeyboardButton("📊 Statistik"), KeyboardButton("ℹ️ Informasi")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def check_user_has_payment_method(user_id: int) -> bool:
    """Cek apakah pengguna sudah mengatur metode pembayaran"""
    user = get_user(user_id)
    if not user:
        return False
    
    required_fields = ['payment_method_type', 'payment_method', 'account_name', 'account_number']
    return all(user.get(field) for field in required_fields)

def get_payment_fee(payment_type: str, payment_method: str) -> int:
    """Dapatkan biaya admin berdasarkan metode pembayaran"""
    if payment_type == 'bank':
        return PAYMENT_METHODS['bank']['options'][payment_method]['fee']
    elif payment_type == 'ewallet':
        return PAYMENT_METHODS['ewallet']['fee']
    return 0

def generate_order_id() -> str:
    """Generate kode transaksi unik"""
    import random
    import string
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_str = ''.join(random.choices(string.digits, k=4))
    return f"ORD-{timestamp}{random_str}"

def get_memo_from_order_id(order_id: str) -> str:
    """Ambil 4 digit terakhir dari Order ID untuk memo"""
    return order_id[-4:]

def format_datetime(dt_string):
    """Format datetime string ke format yang lebih readable"""
    try:
        dt = datetime.strptime(dt_string, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d/%m/%Y %H:%M")
    except:
        return dt_string

async def fetch_ton_price():
    """Ambil harga TON dari CoinGecko"""
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    price_usd = data['the-open-network']['usd']
                    
                    url_idr = "https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=idr"
                    async with session.get(url_idr) as resp_idr:
                        if resp_idr.status == 200:
                            data_idr = await resp_idr.json()
                            usd_to_idr = data_idr['tether']['idr']
                            
                            price_idr_base = price_usd * usd_to_idr
                            price_idr_buy = price_idr_base - MARGIN_PER_TON
                            
                            ton_price_cache['price_usd'] = price_usd
                            ton_price_cache['price_idr'] = price_idr_buy
                            ton_price_cache['last_update'] = datetime.now()
                            
                            logger.info(f"Harga diperbarui: ${price_usd} | Rp {price_idr_buy:,.0f}")
                            return True
        return False
    except Exception as e:
        logger.error(f"Gagal mengambil harga TON: {e}")
        return False

async def get_ton_price():
    """Dapatkan harga TON, perbarui jika perlu"""
    if ton_price_cache['last_update'] is None or \
       (datetime.now() - ton_price_cache['last_update']).seconds > 600:
        await fetch_ton_price()
    
    return ton_price_cache['price_idr']

def get_price_update_time():
    """Dapatkan waktu pembaruan harga terakhir"""
    if ton_price_cache['last_update']:
        return ton_price_cache['last_update'].strftime("%H:%M")
    return "Belum diperbarui"

async def send_transaction_page(message, context: ContextTypes.DEFAULT_TYPE, user_id: int, page: int, is_edit=False):
    """Kirim halaman riwayat transaksi dengan pagination"""
    items_per_page = 2
    offset = (page - 1) * items_per_page
    
    # Ambil semua transaksi
    all_transactions = get_user_transactions(user_id, limit=100)
    total_transactions = len(all_transactions)
    
    if total_transactions == 0:
        text = get_text('no_transactions')
        if is_edit:
            try:
                await message.edit_text(text, parse_mode='HTML')
            except:
                pass
        else:
            await message.reply_text(text, parse_mode='HTML')
        return
    
    # Ambil transaksi untuk halaman ini
    transactions = all_transactions[offset:offset + items_per_page]
    
    trans_list = []
    for trans in transactions:
        if trans['status'] == 'completed':
            status = "✅"
        elif trans['status'] == 'pending':
            status = "⏳"
        else:
            status = "❌"
        
        # Format ringkas
        trans_text = (
            f"{status} <code>{trans['order_id']}</code>\n"
            f"📅 {format_datetime(trans['created_at'])}\n"
            f"💎 {trans['ton_amount']} TON → 💰 Rp {trans['total']:,.0f}\n"
        )
        trans_list.append(trans_text)
    
    transactions_text = "\n".join(trans_list)
    
    total_pages = (total_transactions + items_per_page - 1) // items_per_page
    
    history_text = (
        f"📜 <b>Riwayat Transaksi</b>\n\n"
        f"{transactions_text}\n"
        f"📄 Halaman {page}/{total_pages} • Total: {total_transactions} transaksi"
        + COPYRIGHT_TEXT
    )
    
    # Buat tombol navigasi
    keyboard = []
    nav_buttons = []
    
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Sebelumnya", callback_data=f"history_page_{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton("🔄 Refresh", callback_data=f"history_page_{page}"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("Selanjutnya ➡️", callback_data=f"history_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Tombol quick jump (jika lebih dari 3 halaman)
    if total_pages > 3:
        jump_buttons = []
        if page != 1:
            jump_buttons.append(InlineKeyboardButton("⏮️ Pertama", callback_data="history_page_1"))
        if page != total_pages:
            jump_buttons.append(InlineKeyboardButton("Terakhir ⏭️", callback_data=f"history_page_{total_pages}"))
        if jump_buttons:
            keyboard.append(jump_buttons)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if is_edit:
        try:
            await message.edit_text(history_text, reply_markup=reply_markup, parse_mode='HTML')
        except:
            pass
    else:
        await message.reply_text(history_text, reply_markup=reply_markup, parse_mode='HTML')

async def handle_transaction_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk menampilkan riwayat transaksi (halaman 1)"""
    user_id = update.effective_user.id
    page = 1
    await send_transaction_page(update.message, context, user_id, page, is_edit=False)

async def handle_history_page_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk navigasi halaman riwayat"""
    user_id = query.from_user.id
    callback_data = query.data
    
    # Extract page number
    page = int(callback_data.split("_")[-1])
    
    await send_transaction_page(query.message, context, user_id, page, is_edit=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk perintah /start"""
    user = update.effective_user
    user_id = user.id
    
    save_user(user_id, user.username, user.first_name)
    
    if user.username:
        user_greeting = f"@{user.username}"
    else:
        user_greeting = user.first_name
    
    await fetch_ton_price()
    
    # ============================================================
    # START OF REFERRAL SYSTEM - DETECT REFERRAL PARAMETER
    # ============================================================
    # Cek apakah ada parameter referral
    if context.args and len(context.args) > 0:
        referral_param = context.args[0]
        
        # Format: ref_USERID
        if referral_param.startswith('ref_'):
            try:
                referrer_id = int(referral_param.replace('ref_', ''))
                
                # Simpan referral jika belum pernah direferensikan
                if save_referral(referrer_id, user_id):
                    # Notifikasi ke user yang bergabung
                    await update.message.reply_text(
                        get_text('referral_welcome'),
                        parse_mode='HTML'
                    )
                    
                    # Notifikasi ke referrer
                    referred_name = user.first_name
                    if user.username:
                        referred_name += f" (@{user.username})"
                    
                    try:
                        await context.bot.send_message(
                            chat_id=referrer_id,
                            text=get_text('referral_new_user', referred_name=referred_name),
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify referrer {referrer_id}: {e}")
                    
                    logger.info(f"New referral: {referrer_id} -> {user_id}")
            except ValueError:
                pass  # Invalid referral parameter
    # ============================================================
    # END OF REFERRAL SYSTEM - DETECT REFERRAL PARAMETER
    # ============================================================
    
    welcome_text = get_text('welcome', user_greeting=user_greeting)
    context.user_data.clear()
    
    await update.message.reply_text(
        welcome_text, 
        reply_markup=get_main_button_keyboard(),
        parse_mode='HTML'
    )

# ============================================================
# START OF HELP COMMAND HANDLER
# ============================================================
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk perintah /help"""
    price = await get_ton_price()
    
    help_text = (
        "📖 <b>PANDUAN PENGGUNAAN BOT</b>\n\n"
        "🔹 <b>Cara Jual TON:</b>\n"
        "1️⃣ Klik <b>💳 Atur Pembayaran</b> untuk setup rekening\n"
        "2️⃣ Klik <b>💎 Jual TON</b> untuk memulai\n"
        "3️⃣ Masukkan jumlah TON yang ingin dijual\n"
        "4️⃣ Kirim TON ke alamat yang diberikan\n"
        "5️⃣ Upload bukti transfer\n"
        "6️⃣ Tunggu admin memproses pembayaran\n\n"
        "🔹 <b>Menu Tersedia:</b>\n"
        "• 💎 <b>Jual TON</b> - Jual Toncoin Anda\n"
        "• 💳 <b>Atur Pembayaran</b> - Setup metode pembayaran\n"
        "• 📜 <b>Riwayat</b> - Lihat riwayat transaksi\n"
        "• 💰 <b>Saldo</b> - Cek saldo rujukan\n"
        "• 📊 <b>Statistik</b> - Lihat statistik bot\n"
        "• ℹ️ <b>Informasi</b> - Info harga dan metode pembayaran\n\n"
        "🔹 <b>Sistem Rujukan:</b>\n"
        "• Bagikan link rujukan Anda\n"
        "• Dapatkan 0.3% dari setiap transaksi rujukan\n"
        "• Tarik saldo saat mencapai Rp 25.000\n\n"
        f"💰 <b>Harga saat ini:</b> Rp {price:,.0f}/TON\n\n"
        "📞 <b>Bantuan:</b> @" + ADMIN_USERNAME
        + COPYRIGHT_TEXT
    )
    
    await update.message.reply_text(
        help_text,
        reply_markup=get_main_button_keyboard(),
        parse_mode='HTML'
    )
# ============================================================
# END OF HELP COMMAND HANDLER
# ============================================================

async def handle_button_press(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk tombol tekan dari keyboard"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if text == "💎 Jual TON":
        if not check_user_has_payment_method(user_id):
            setup_text = get_text('setup_payment_required')
            keyboard = [[InlineKeyboardButton("💳 Atur Pembayaran", callback_data="setup_payment_method")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(setup_text, reply_markup=reply_markup, parse_mode='HTML')
            return
        
        await fetch_ton_price()
        price = await get_ton_price()
        
        # Hitung maksimal TON berdasarkan metode pembayaran user
        user_info = get_user(user_id)
        max_ton = calculate_max_ton(price, user_info['payment_method_type'], user_info['payment_method'])
        
        input_text = get_text('input_ton_amount', 
                             price=price, 
                             min_ton=MIN_TON,
                             max_ton=max_ton,
                             max_idr=MAX_TRANSACTION_IDR)
        
        keyboard = [[InlineKeyboardButton("❌ Batalkan", callback_data="cancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        sent_msg = await update.message.reply_text(input_text, reply_markup=reply_markup, parse_mode='HTML')
        context.user_data['awaiting_ton_amount'] = True
        context.user_data['last_message_id'] = sent_msg.message_id
    
    elif text == "💳 Atur Pembayaran":
        await handle_setup_payment_method(update, context)
    
    elif text == "ℹ️ Informasi":
        await fetch_ton_price()
        price = await get_ton_price()
        info_text = get_text('help_text', price=price)
        await update.message.reply_text(info_text, parse_mode='HTML')
    
    elif text == "📊 Statistik":
        await handle_public_stats(update, context)
    
    elif text == "📜 Riwayat":
        await handle_transaction_history(update, context)
    
    # ============================================================
    # START OF REFERRAL SYSTEM - SALDO BUTTON HANDLER
    # ============================================================
    elif text == "💰 Saldo":
        await handle_referral_balance(update, context)
    # ============================================================
    # END OF REFERRAL SYSTEM - SALDO BUTTON HANDLER
    # ============================================================

async def handle_setup_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk pengaturan metode pembayaran"""
    text = get_text('select_payment_method')
    
    keyboard = [
        [InlineKeyboardButton("🏦 Transfer Bank", callback_data="setup_bank")],
        [InlineKeyboardButton("📱 E-Wallet", callback_data="setup_ewallet")],
        [InlineKeyboardButton("❌ Batalkan", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk callback tombol inline"""
    query = update.callback_query
    user_id = query.from_user.id
    
    # ============================================================
    # START OF CALLBACK HANDLERS THAT NEED CUSTOM ANSWER
    # Beberapa callback memerlukan custom answer, jadi tidak di-answer di sini
    # ============================================================
    callbacks_with_custom_answer = [
        "withdrawal_insufficient",
        "confirm_broadcast_yes",
        "confirm_broadcast_no"
    ]
    
    # Cek apakah callback ini memerlukan custom answer
    needs_custom_answer = any(query.data.startswith(cb) for cb in callbacks_with_custom_answer)
    
    if not needs_custom_answer:
        await query.answer()
    # ============================================================
    # END OF CALLBACK HANDLERS THAT NEED CUSTOM ANSWER
    # ============================================================
    
    if query.data == "cancel":
        try:
            await query.message.delete()
        except:
            pass
        
        text = get_text('order_cancelled')
        await context.bot.send_message(chat_id=query.message.chat_id, text=text, parse_mode='HTML')
        
        context.user_data.clear()
        if user_id in user_payment_info:
            del user_payment_info[user_id]
        if user_id in pending_orders:
            del pending_orders[user_id]
    
    elif query.data.startswith("history_page_"):
        await handle_history_page_callback(query, context)
    
    elif query.data == "setup_payment_method":
        await handle_setup_payment_method_inline(query, context)
    
    elif query.data == "setup_bank":
        await handle_setup_bank_selection(query, context)
    
    elif query.data == "setup_ewallet":
        await handle_setup_ewallet_selection(query, context)
    
    elif query.data.startswith("setup_bank_"):
        bank_name = query.data.replace("setup_bank_", "")
        await handle_setup_bank_selected(query, context, bank_name)
    
    elif query.data.startswith("setup_ewallet_"):
        ewallet_name = query.data.replace("setup_ewallet_", "")
        await handle_setup_ewallet_selected(query, context, ewallet_name)
    
    elif query.data == "confirm_setup_yes":
        await handle_confirm_setup_payment_data(query, context)
    
    elif query.data == "confirm_setup_no":
        text = get_text('order_cancelled')
        try:
            await query.message.edit_text(text, parse_mode='HTML')
        except:
            pass
        context.user_data['payment_step'] = None
    
    elif query.data == "ton_sent_yes":
        await handle_ton_sent(query, context)
    
    elif query.data == "ton_sent_no":
        text = get_text('order_cancelled')
        try:
            await query.message.edit_text(text, parse_mode='HTML')
        except:
            pass
        if user_id in pending_orders:
            del pending_orders[user_id]
    
    elif query.data == "refresh_stats":
        await handle_owner_stats_refresh(query, context)
    
    elif query.data == "start_sell_ton":
        await handle_start_sell_ton(query, context)
    
    # ============================================================
    # START OF REFERRAL SYSTEM - CALLBACK HANDLERS
    # ============================================================
    elif query.data == "withdrawal_request":
        await handle_withdrawal_request(query, context)
    
    elif query.data == "confirm_withdrawal_yes":
        await handle_confirm_withdrawal(query, context)
    
    elif query.data == "confirm_withdrawal_no":
        text = get_text('order_cancelled')
        try:
            await query.message.edit_text(text, parse_mode='HTML')
        except:
            pass
        context.user_data['withdrawal_pending'] = None
    
    # ============================================================
    # START OF WITHDRAWAL INSUFFICIENT BALANCE HANDLER
    # ============================================================
    elif query.data == "withdrawal_insufficient":
        # Tampilkan pesan saldo tidak cukup dengan respon yang jelas
        referral_stats = get_referral_stats(user_id)
        balance = referral_stats['referral_balance']
        
        # Tampilkan popup alert terlebih dahulu
        await query.answer(f"❌ Saldo tidak mencukupi! Minimal Rp {MIN_WITHDRAWAL_AMOUNT:,.0f}", show_alert=True)
        
        # Dapatkan informasi untuk menampilkan pesan lengkap
        bot_username = (await context.bot.get_me()).username
        total_referrals = referral_stats['total_referrals']
        
        # Buat pesan yang informatif tentang saldo tidak cukup
        insufficient_response = (
            f"❌ <b>Saldo Tidak Mencukupi untuk Penarikan</b>\n\n"
            f"💵 <b>Saldo Anda saat ini:</b> Rp {balance:,.0f}\n"
            f"📊 <b>Minimal Penarikan:</b> Rp {MIN_WITHDRAWAL_AMOUNT:,.0f}\n"
            f"📉 <b>Kekurangan:</b> Rp {(MIN_WITHDRAWAL_AMOUNT - balance):,.0f}\n\n"
            f"👥 <b>Total Rujukan:</b> {total_referrals} orang\n\n"
            f"💡 <b>Tips untuk mencapai minimal penarikan:</b>\n"
            f"• Bagikan link rujukan Anda ke teman-teman\n"
            f"• Dapatkan 0.3% dari setiap transaksi rujukan\n\n"
            f"🔗 <b>Link Rujukan Anda:</b>\n"
            f"<code>https://t.me/{bot_username}?start=ref_{user_id}</code>\n\n"
            f"<i>Kumpulkan lebih banyak rujukan untuk mencapai batas minimal!</i>"
            + COPYRIGHT_TEXT
        )
        
        # Tombol untuk kembali
        keyboard = [
            [InlineKeyboardButton("🔙 Kembali ke Saldo", callback_data="back_to_balance")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.message.edit_text(insufficient_response, reply_markup=reply_markup, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Error showing insufficient balance message: {e}")
    # ============================================================
    # END OF WITHDRAWAL INSUFFICIENT BALANCE HANDLER
    # ============================================================
    # ============================================================
    # END OF REFERRAL SYSTEM - CALLBACK HANDLERS
    # ============================================================
    
    # ============================================================
    # START OF BACK TO BALANCE CALLBACK HANDLER
    # ============================================================
    elif query.data == "back_to_balance":
        # Kembali ke halaman saldo rujukan
        bot_username = (await context.bot.get_me()).username
        referral_stats = get_referral_stats(user_id)
        balance = referral_stats['referral_balance']
        total_referrals = referral_stats['total_referrals']
        
        balance_text = get_text('referral_balance',
                               balance=balance,
                               total_referrals=total_referrals,
                               bot_username=bot_username,
                               user_id=user_id)
        
        # Buat tombol Penarikan
        keyboard = []
        
        if balance >= MIN_WITHDRAWAL_AMOUNT:
            keyboard.append([InlineKeyboardButton("💸 Penarikan", callback_data="withdrawal_request")])
        else:
            keyboard.append([InlineKeyboardButton(f"💸 Penarikan (Min. Rp {MIN_WITHDRAWAL_AMOUNT:,.0f})", callback_data="withdrawal_insufficient")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.message.edit_text(balance_text, reply_markup=reply_markup, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Error returning to balance page: {e}")
    # ============================================================
    # END OF BACK TO BALANCE CALLBACK HANDLER
    # ============================================================
    
    # ============================================================
    # START OF BROADCAST SYSTEM - CALLBACK HANDLERS
    # ============================================================
    elif query.data.startswith("confirm_broadcast_"):
        await handle_broadcast_callback(query, context)
    # ============================================================
    # END OF BROADCAST SYSTEM - CALLBACK HANDLERS
    # ============================================================

async def handle_setup_payment_method_inline(query, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk pengaturan metode pembayaran dari tombol inline"""
    text = get_text('select_payment_method')
    
    keyboard = [
        [InlineKeyboardButton("🏦 Transfer Bank", callback_data="setup_bank")],
        [InlineKeyboardButton("📱 E-Wallet", callback_data="setup_ewallet")],
        [InlineKeyboardButton("❌ Batalkan", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='HTML')
    except:
        pass

async def handle_setup_bank_selection(query, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk menampilkan pilihan bank"""
    text = get_text('select_bank')
    
    keyboard = []
    for bank_name, bank_info in PAYMENT_METHODS['bank']['options'].items():
        fee_text = f"Gratis" if bank_info['fee'] == 0 else f"Rp {bank_info['fee']:,}"
        keyboard.append([InlineKeyboardButton(
            f"🏦 {bank_name} ({fee_text})", 
            callback_data=f"setup_bank_{bank_name}"
        )])
    keyboard.append([InlineKeyboardButton("🔙 Kembali", callback_data="setup_payment_method")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='HTML')
    except:
        pass

async def handle_setup_ewallet_selection(query, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk menampilkan pilihan e-wallet"""
    text = get_text('select_ewallet')
    
    keyboard = []
    for ewallet in PAYMENT_METHODS['ewallet']['options']:
        keyboard.append([InlineKeyboardButton(f"📱 {ewallet}", callback_data=f"setup_ewallet_{ewallet}")])
    keyboard.append([InlineKeyboardButton("🔙 Kembali", callback_data="setup_payment_method")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='HTML')
    except:
        pass

async def handle_setup_bank_selected(query, context: ContextTypes.DEFAULT_TYPE, bank_name: str):
    """Handler ketika bank dipilih"""
    user_id = query.from_user.id
    
    if user_id not in user_payment_info:
        user_payment_info[user_id] = {}
    
    user_payment_info[user_id]['setup_method_type'] = 'bank'
    user_payment_info[user_id]['setup_method'] = bank_name
    
    text = get_text('input_account_name', method=bank_name)
    
    try:
        await query.message.edit_text(text, parse_mode='HTML')
    except:
        pass
    
    context.user_data['payment_step'] = 'setup_awaiting_name'

async def handle_setup_ewallet_selected(query, context: ContextTypes.DEFAULT_TYPE, ewallet_name: str):
    """Handler ketika e-wallet dipilih"""
    user_id = query.from_user.id
    
    if user_id not in user_payment_info:
        user_payment_info[user_id] = {}
    
    user_payment_info[user_id]['setup_method_type'] = 'ewallet'
    user_payment_info[user_id]['setup_method'] = ewallet_name
    
    text = get_text('input_account_name', method=ewallet_name)
    
    try:
        await query.message.edit_text(text, parse_mode='HTML')
    except:
        pass
    
    context.user_data['payment_step'] = 'setup_awaiting_name'

async def handle_confirm_setup_payment_data(query, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk konfirmasi setup data pembayaran"""
    user_id = query.from_user.id
    
    if user_id not in user_payment_info:
        await query.message.edit_text("❌ <i>Sesi berakhir.</i>", parse_mode='HTML')
        return
    
    payment_data = user_payment_info[user_id]
    
    save_user(user_id, query.from_user.username, query.from_user.first_name, {
        'payment_method_type': payment_data['setup_method_type'],
        'payment_method': payment_data['setup_method'],
        'account_name': payment_data['setup_account_name'],
        'account_number': payment_data['setup_account_number']
    })
    
    text = get_text('payment_method_saved',
                   method=payment_data['setup_method'],
                   name=payment_data['setup_account_name'],
                   number=payment_data['setup_account_number'])
    
    keyboard = [[InlineKeyboardButton("💎 Jual TON", callback_data="start_sell_ton")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.message.edit_text(text, reply_markup=reply_markup, parse_mode='HTML')
    except:
        pass
    
    del user_payment_info[user_id]
    context.user_data['payment_step'] = None
    
    logger.info(f"User {user_id} setup payment method: {payment_data['setup_method']}")

async def handle_ton_sent(query, context: ContextTypes.DEFAULT_TYPE):
    """Handler ketika user klik sudah mengirim TON"""
    user_id = query.from_user.id
    
    if user_id not in pending_orders:
        await query.message.edit_text("❌ <i>Pesanan tidak ditemukan.</i>", parse_mode='HTML')
        return
    
    order_data = pending_orders[user_id]
    memo = order_data.get('memo', '')
    
    text = get_text('waiting_payment_proof', memo=memo)
    
    try:
        await query.message.edit_text(text, parse_mode='HTML')
    except:
        pass
    
    context.user_data['awaiting_proof'] = True

async def handle_start_sell_ton(query, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk tombol Jual TON setelah setup payment"""
    user_id = query.from_user.id
    
    price = await get_ton_price()
    
    # Hitung maksimal TON
    user_info = get_user(user_id)
    max_ton = calculate_max_ton(price, user_info['payment_method_type'], user_info['payment_method'])
    
    input_text = get_text('input_ton_amount', 
                         price=price, 
                         min_ton=MIN_TON,
                         max_ton=max_ton,
                         max_idr=MAX_TRANSACTION_IDR)
    
    keyboard = [[InlineKeyboardButton("❌ Batalkan", callback_data="cancel")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.message.edit_text(input_text, reply_markup=reply_markup, parse_mode='HTML')
    except:
        pass
    
    context.user_data['awaiting_ton_amount'] = True

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk pesan teks dan foto"""
    user_id = update.effective_user.id
    
    # ============================================================
    # START OF PHOTO HANDLING
    # ============================================================
    # Handle foto terlebih dahulu
    if update.message.photo:
        if context.user_data.get('awaiting_proof'):
            await handle_payment_proof(update, context)
            return
        else:
            # Foto dikirim di luar konteks transaksi
            await update.message.reply_text(
                "📷 <i>Foto diterima, tapi saat ini tidak ada transaksi yang memerlukan bukti transfer.</i>\n\n"
                "💡 <b>Gunakan menu di bawah untuk memulai transaksi.</b>",
                parse_mode='HTML',
                reply_markup=get_main_button_keyboard()
            )
            return
    # ============================================================
    # END OF PHOTO HANDLING
    # ============================================================
    
    # Pastikan text tidak None sebelum melanjutkan
    text = update.message.text
    if not text:
        return
    
    # Jika user sedang menunggu bukti foto tapi mengirim teks
    if context.user_data.get('awaiting_proof'):
        await update.message.reply_text(get_text('please_send_photo'), parse_mode='HTML')
        return
    
    button_texts = [
        "💎 Jual TON",
        "💳 Atur Pembayaran",
        "📊 Statistik",
        "ℹ️ Informasi",
        "📜 Riwayat",
        "💰 Saldo"  # Tambah tombol Saldo
    ]
    
    if text in button_texts:
        await handle_button_press(update, context)
        return
    
    if user_id == OWNER_USER_ID:
        if text.lower() == 'stats':
            await handle_owner_stats(update, context)
            return
        elif text.lower().startswith('selesai '):
            await handle_admin_confirmation(update, context)
            return
        elif text.lower().startswith('bayarwd '):
            await handle_admin_withdrawal_confirmation(update, context)
            return
    
    payment_step = context.user_data.get('payment_step')
    
    if payment_step == 'setup_awaiting_name':
        user_payment_info[user_id]['setup_account_name'] = text
        
        method = user_payment_info[user_id]['setup_method']
        name = text
        
        response_text = get_text('input_account_number', method=method, name=name)
        await update.message.reply_text(response_text, parse_mode='HTML')
        
        context.user_data['payment_step'] = 'setup_awaiting_number'
        return
    
    elif payment_step == 'setup_awaiting_number':
        user_payment_info[user_id]['setup_account_number'] = text
        
        payment_data = user_payment_info[user_id]
        
        confirm_text = get_text('confirm_payment_info',
                               method=payment_data['setup_method'],
                               name=payment_data['setup_account_name'],
                               number=payment_data['setup_account_number'])
        
        keyboard = [
            [InlineKeyboardButton("✅ Ya, Benar", callback_data="confirm_setup_yes")],
            [InlineKeyboardButton("❌ Tidak, Batalkan", callback_data="confirm_setup_no")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(confirm_text, reply_markup=reply_markup, parse_mode='HTML')
        
        context.user_data['payment_step'] = None
        return
    
    if context.user_data.get('awaiting_ton_amount'):
        try:
            ton_amount = float(update.message.text.replace(',', '.'))
            
            if ton_amount < MIN_TON:
                await update.message.reply_text(get_text('invalid_amount', min_ton=MIN_TON), parse_mode='HTML')
                return
            
            price = await get_ton_price()
            
            # Validasi maksimal TON
            user_info = get_user(user_id)
            max_ton = calculate_max_ton(price, user_info['payment_method_type'], user_info['payment_method'])
            
            if ton_amount > max_ton:
                await update.message.reply_text(
                    get_text('invalid_max_amount', max_ton=max_ton, max_idr=MAX_TRANSACTION_IDR), 
                    parse_mode='HTML'
                )
                return
            
            subtotal = ton_amount * price
            
            payment_method_type = user_info.get('payment_method_type')
            payment_method = user_info.get('payment_method')
            fee = get_payment_fee(payment_method_type, payment_method)
            
            total = subtotal - fee
            
            order_id = generate_order_id()
            memo = get_memo_from_order_id(order_id)
            
            pending_orders[user_id] = {
                'order_id': order_id,
                'memo': memo,
                'ton_amount': ton_amount,
                'price_per_ton': price,
                'fee': fee,
                'total': total,
                'payment_method_type': payment_method_type,
                'payment_method': payment_method,
                'account_name': user_info.get('account_name'),
                'account_number': user_info.get('account_number'),
                'timestamp': datetime.now()
            }
            
            try:
                if 'last_message_id' in context.user_data:
                    await context.bot.delete_message(
                        chat_id=update.effective_chat.id,
                        message_id=context.user_data['last_message_id']
                    )
            except:
                pass
            
            try:
                await update.message.delete()
            except:
                pass
            
            instruction_text = get_text('send_ton_instruction',
                                       ton_amount=ton_amount,
                                       price_per_ton=price,
                                       fee=fee,
                                       total=total,
                                       wallet=YOUR_TON_WALLET,
                                       memo=memo)
            
            ton_deeplink = f"ton://transfer/{YOUR_TON_WALLET}?amount={int(ton_amount * 1000000000)}&text={memo}"
            
            keyboard = [
                [InlineKeyboardButton("💎 Bayar Sekarang", url=ton_deeplink)],
                [InlineKeyboardButton("✅ Sudah Kirim", callback_data="ton_sent_yes")],
                [InlineKeyboardButton("❌ Batalkan", callback_data="ton_sent_no")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=instruction_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            
            context.user_data['awaiting_ton_amount'] = False
            
        except ValueError:
            await update.message.reply_text(get_text('invalid_number'), parse_mode='HTML')
    else:
        # ============================================================
        # START OF FALLBACK HANDLER FOR UNRECOGNIZED MESSAGES
        # ============================================================
        # Pesan tidak dikenali, tampilkan bantuan singkat
        fallback_text = (
            "🤖 <i>Pesan tidak dikenali.</i>\n\n"
            "💡 <b>Gunakan menu di bawah untuk:</b>\n"
            "• 💎 <b>Jual TON</b> - Jual Toncoin Anda\n"
            "• 💳 <b>Atur Pembayaran</b> - Setup metode pembayaran\n"
            "• 📜 <b>Riwayat</b> - Lihat transaksi\n"
            "• 💰 <b>Saldo</b> - Cek saldo rujukan\n"
            "• 📊 <b>Statistik</b> - Lihat statistik bot\n"
            "• ℹ️ <b>Informasi</b> - Info lebih lanjut\n\n"
            "<i>Atau ketik /start untuk memulai ulang.</i>"
            + COPYRIGHT_TEXT
        )
        await update.message.reply_text(
            fallback_text, 
            parse_mode='HTML',
            reply_markup=get_main_button_keyboard()
        )
        # ============================================================
        # END OF FALLBACK HANDLER FOR UNRECOGNIZED MESSAGES
        # ============================================================

async def handle_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk foto bukti transfer"""
    user_id = update.effective_user.id
    user = update.effective_user
    
    if user_id not in pending_orders:
        await update.message.reply_text("❌ <i>Tidak ada pesanan aktif.</i>", parse_mode='HTML')
        return
    
    order_data = pending_orders[user_id]
    order_id = order_data['order_id']
    
    confirm_text = get_text('proof_received',
                           ton_amount=order_data['ton_amount'],
                           total=order_data['total'],
                           payment_method=order_data['payment_method'],
                           order_id=order_id)
    
    await update.message.reply_text(confirm_text, parse_mode='HTML')
    
    save_transaction(order_data, user_id, user.username, user.first_name)
    
    user_info = f"{user.first_name}"
    if user.username:
        user_info += f" (@{user.username})"
    
    payment_info = (
        f"{'🏦 Bank' if order_data['payment_method_type'] == 'bank' else '📱 E-Wallet'}: {order_data['payment_method']}\n"
        f"👤 <b>Nama:</b> {order_data['account_name']}\n"
        f"🔢 <b>Nomor:</b> <code>{order_data['account_number']}</code>"
    )
    
    admin_text = get_text('admin_notification',
                         user_info=user_info,
                         user_id=user_id,
                         ton_amount=order_data['ton_amount'],
                         memo=order_data.get('memo', ''),
                         total=order_data['total'],
                         payment_info=payment_info,
                         order_id=order_id)
    
    try:
        photo = update.message.photo[-1]
        notification_msg = await context.bot.send_photo(
            chat_id=OWNER_USER_ID,
            photo=photo.file_id,
            caption=admin_text,
            parse_mode='HTML'
        )
        
        # Simpan message_id notifikasi untuk dihapus nanti saat transaksi selesai
        notification_messages[order_id] = notification_msg.message_id
        
        logger.info(f"Bukti transfer diterima dari user {user_id}, order {order_id}")
        
    except Exception as e:
        logger.error(f"Gagal kirim notifikasi ke owner: {e}")
    
    del pending_orders[user_id]
    context.user_data.clear()

async def handle_public_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk statistik publik"""
    price = await get_ton_price()
    stats = get_statistics()
    update_time = datetime.now().strftime("%d/%m/%Y %H:%M")
    
    stats_text = get_text('public_stats',
                         total_users=stats['total_users'],
                         price=price,
                         completed_trans=stats['completed_transactions'],
                         update_time=update_time)
    
    await update.message.reply_text(stats_text, parse_mode='HTML')

# ============================================================
# START OF REFERRAL SYSTEM - HANDLERS
# ============================================================
async def handle_referral_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk menampilkan saldo rujukan"""
    user_id = update.effective_user.id
    bot_username = (await context.bot.get_me()).username
    
    # Dapatkan statistik referral
    referral_stats = get_referral_stats(user_id)
    balance = referral_stats['referral_balance']
    total_referrals = referral_stats['total_referrals']
    
    balance_text = get_text('referral_balance',
                           balance=balance,
                           total_referrals=total_referrals,
                           bot_username=bot_username,
                           user_id=user_id)
    
    # Buat tombol Penarikan
    keyboard = []
    
    if balance >= MIN_WITHDRAWAL_AMOUNT:
        # Tombol aktif jika saldo >= 25.000
        keyboard.append([InlineKeyboardButton("💸 Penarikan", callback_data="withdrawal_request")])
    else:
        # Tombol nonaktif dengan pesan
        keyboard.append([InlineKeyboardButton(f"💸 Penarikan (Min. Rp {MIN_WITHDRAWAL_AMOUNT:,.0f})", callback_data="withdrawal_insufficient")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(balance_text, reply_markup=reply_markup, parse_mode='HTML')

async def handle_withdrawal_request(query, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk permintaan penarikan"""
    user_id = query.from_user.id
    
    # Cek saldo
    referral_stats = get_referral_stats(user_id)
    balance = referral_stats['referral_balance']
    
    if balance < MIN_WITHDRAWAL_AMOUNT:
        insufficient_text = get_text('withdrawal_insufficient',
                                    balance=balance,
                                    min_amount=MIN_WITHDRAWAL_AMOUNT)
        try:
            await query.message.edit_text(insufficient_text, parse_mode='HTML')
        except:
            pass
        return
    
    # Cek apakah user sudah punya metode pembayaran
    user_info = get_user(user_id)
    
    if not user_info or not user_info.get('payment_method'):
        no_payment_text = get_text('no_payment_method_withdrawal')
        keyboard = [[InlineKeyboardButton("💳 Atur Pembayaran", callback_data="setup_payment_method")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_text(no_payment_text, reply_markup=reply_markup, parse_mode='HTML')
        except:
            pass
        return
    
    # Tampilkan konfirmasi penarikan
    confirm_text = get_text('withdrawal_confirm',
                           amount=balance,
                           payment_method=user_info['payment_method'],
                           account_name=user_info['account_name'],
                           account_number=user_info['account_number'])
    
    keyboard = [
        [InlineKeyboardButton("✅ Ya, Tarik Saldo", callback_data="confirm_withdrawal_yes")],
        [InlineKeyboardButton("❌ Batalkan", callback_data="confirm_withdrawal_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Simpan data penarikan sementara
    context.user_data['withdrawal_pending'] = {
        'amount': balance,
        'payment_method': user_info['payment_method'],
        'account_name': user_info['account_name'],
        'account_number': user_info['account_number']
    }
    
    try:
        await query.message.edit_text(confirm_text, reply_markup=reply_markup, parse_mode='HTML')
    except:
        pass

async def handle_confirm_withdrawal(query, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk konfirmasi penarikan"""
    user_id = query.from_user.id
    user = query.from_user
    
    withdrawal_data = context.user_data.get('withdrawal_pending')
    
    if not withdrawal_data:
        await query.message.edit_text("❌ <i>Sesi berakhir. Silakan coba lagi.</i>", parse_mode='HTML')
        return
    
    amount = withdrawal_data['amount']
    payment_method = withdrawal_data['payment_method']
    account_name = withdrawal_data['account_name']
    account_number = withdrawal_data['account_number']
    
    # Kurangi saldo
    if not deduct_referral_balance(user_id, amount):
        await query.message.edit_text("❌ <i>Gagal memproses penarikan. Saldo tidak mencukupi.</i>", parse_mode='HTML')
        return
    
    # Simpan permintaan penarikan
    request_id = save_withdrawal_request(user_id, amount, payment_method, account_name, account_number)
    
    if not request_id:
        # Kembalikan saldo jika gagal
        add_referral_earning(user_id, amount)
        await query.message.edit_text("❌ <i>Gagal menyimpan permintaan penarikan.</i>", parse_mode='HTML')
        return
    
    # Notifikasi ke user
    success_text = get_text('withdrawal_request_sent',
                           amount=amount,
                           payment_method=payment_method,
                           account_name=account_name,
                           account_number=account_number)
    
    try:
        await query.message.edit_text(success_text, parse_mode='HTML')
    except:
        pass
    
    # Notifikasi ke admin/owner
    user_info = f"{user.first_name}"
    if user.username:
        user_info += f" (@{user.username})"
    
    admin_text = get_text('withdrawal_admin_notification',
                         user_info=user_info,
                         user_id=user_id,
                         amount=amount,
                         payment_method=payment_method,
                         account_name=account_name,
                         account_number=account_number,
                         request_id=request_id)
    
    try:
        await context.bot.send_message(
            chat_id=OWNER_USER_ID,
            text=admin_text,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Failed to notify admin about withdrawal: {e}")
    
    # Bersihkan data sementara
    context.user_data['withdrawal_pending'] = None
    
    logger.info(f"Withdrawal request created: user {user_id}, amount {amount}, request_id {request_id}")
# ============================================================
# END OF REFERRAL SYSTEM - HANDLERS
# ============================================================

async def handle_owner_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk owner melihat statistik bot"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_USER_ID:
        await update.message.reply_text(get_text('owner_only'), parse_mode='HTML')
        return
    
    price = await get_ton_price()
    stats = get_statistics()
    update_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    stats_text = get_text('stats_menu',
                         total_users=stats['total_users'],
                         price=price,
                         completed_trans=stats['completed_transactions'],
                         pending_trans=stats['pending_transactions'],
                         update_time=update_time)
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_stats")],
        [InlineKeyboardButton("❌ Tutup", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(stats_text, reply_markup=reply_markup, parse_mode='HTML')

async def handle_owner_stats_refresh(query, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk refresh statistik"""
    await fetch_ton_price()
    price = await get_ton_price()
    stats = get_statistics()
    update_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    stats_text = get_text('stats_menu',
                         total_users=stats['total_users'],
                         price=price,
                         completed_trans=stats['completed_transactions'],
                         pending_trans=stats['pending_transactions'],
                         update_time=update_time)
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_stats")],
        [InlineKeyboardButton("❌ Tutup", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await query.message.edit_text(stats_text, reply_markup=reply_markup, parse_mode='HTML')
    except:
        pass

async def handle_admin_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk owner konfirmasi transaksi selesai"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_USER_ID:
        return
    
    text = update.message.text.strip()
    
    if not text.lower().startswith('selesai '):
        return
    
    parts = text.split(' ', 1)
    if len(parts) != 2:
        await update.message.reply_text(get_text('invalid_format'), parse_mode='HTML')
        return
    
    order_id = parts[1].strip()
    
    transaction = get_transaction(order_id)
    
    if not transaction:
        await update.message.reply_text(get_text('order_not_found'), parse_mode='HTML')
        return
    
    target_user_id = transaction['user_id']
    ton_amount = transaction['ton_amount']
    total = transaction['total']
    first_name = transaction['first_name']
    username = transaction.get('username')
    
    user_notification = get_text('user_payment_received',
                                 ton_amount=ton_amount,
                                 total=total,
                                 channel=TESTIMONI_CHANNEL)
    
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=user_notification,
            parse_mode='HTML'
        )
        
        user_mention = f"@{username}" if username else f"{first_name} (ID: {target_user_id})"
        admin_response = get_text('admin_confirm_success',
                                 user_mention=user_mention,
                                 total=total)
        
        await update.message.reply_text(admin_response, parse_mode='HTML')
        
        logger.info(f"Transaksi {order_id} selesai untuk user {target_user_id}")
        
        complete_transaction(order_id)
        
        # ============================================================
        # HAPUS NOTIFIKASI TRANSAKSI OTOMATIS
        # ============================================================
        if order_id in notification_messages:
            try:
                await context.bot.delete_message(
                    chat_id=OWNER_USER_ID,
                    message_id=notification_messages[order_id]
                )
                del notification_messages[order_id]
                logger.info(f"Notifikasi transaksi {order_id} berhasil dihapus")
            except Exception as e:
                logger.error(f"Gagal menghapus notifikasi transaksi {order_id}: {e}")
        # ============================================================
        # END OF HAPUS NOTIFIKASI TRANSAKSI OTOMATIS
        # ============================================================
        
        # ============================================================
        # START OF REFERRAL SYSTEM - NOTIFY REFERRER
        # ============================================================
        # Cek apakah user yang bertransaksi memiliki referrer
        referrer_id = get_referrer(target_user_id)
        if referrer_id:
            # Hitung penghasilan referral
            referral_earning = total * (REFERRAL_PERCENTAGE / 100)
            
            # Dapatkan saldo baru referrer
            referrer_stats = get_referral_stats(referrer_id)
            new_balance = referrer_stats['referral_balance']
            
            # Kirim notifikasi ke referrer
            try:
                referral_notif = get_text('referral_earning_notification',
                                         amount=referral_earning,
                                         new_balance=new_balance)
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=referral_notif,
                    parse_mode='HTML'
                )
                logger.info(f"Referral earning notification sent to {referrer_id}: Rp {referral_earning:,.0f}")
            except Exception as e:
                logger.error(f"Failed to notify referrer {referrer_id}: {e}")
        # ============================================================
        # END OF REFERRAL SYSTEM - NOTIFY REFERRER
        # ============================================================
        
    except Exception as e:
        logger.error(f"Gagal kirim konfirmasi ke user {target_user_id}: {e}")
        await update.message.reply_text(
            f"❌ <i>Gagal mengirim notifikasi ke user!</i>\n<code>Error: {str(e)}</code>",
            parse_mode='HTML'
        )

# ============================================================
# START OF ADMIN WITHDRAWAL CONFIRMATION HANDLER
# ============================================================
async def handle_admin_withdrawal_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk admin konfirmasi penarikan selesai"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_USER_ID:
        return
    
    text = update.message.text.strip()
    
    if not text.lower().startswith('bayarwd '):
        return
    
    parts = text.split(' ', 1)
    if len(parts) != 2:
        await update.message.reply_text(get_text('withdrawal_invalid_format'), parse_mode='HTML')
        return
    
    request_id_str = parts[1].strip()
    
    # Parse request_id dari format WD-12345
    if request_id_str.upper().startswith('WD-'):
        try:
            request_id = int(request_id_str[3:])
        except ValueError:
            await update.message.reply_text(get_text('withdrawal_invalid_format'), parse_mode='HTML')
            return
    else:
        try:
            request_id = int(request_id_str)
        except ValueError:
            await update.message.reply_text(get_text('withdrawal_invalid_format'), parse_mode='HTML')
            return
    
    # Ambil data withdrawal request
    withdrawal = get_withdrawal_request(request_id)
    
    if not withdrawal:
        await update.message.reply_text(get_text('withdrawal_not_found'), parse_mode='HTML')
        return
    
    if withdrawal['status'] == 'completed':
        await update.message.reply_text("⚠️ <i>Penarikan ini sudah dikonfirmasi sebelumnya.</i>", parse_mode='HTML')
        return
    
    target_user_id = withdrawal['user_id']
    amount = withdrawal['amount']
    payment_method = withdrawal['payment_method']
    account_name = withdrawal['account_name']
    account_number = withdrawal['account_number']
    first_name = withdrawal['first_name']
    username = withdrawal.get('username')
    
    # Tandai withdrawal sebagai selesai
    if not complete_withdrawal_request(request_id):
        await update.message.reply_text("❌ <i>Gagal mengupdate status penarikan.</i>", parse_mode='HTML')
        return
    
    # Kirim notifikasi ke user
    user_notification = get_text('withdrawal_completed',
                                 amount=amount,
                                 payment_method=payment_method,
                                 account_name=account_name,
                                 account_number=account_number)
    
    try:
        await context.bot.send_message(
            chat_id=target_user_id,
            text=user_notification,
            parse_mode='HTML'
        )
        
        user_mention = f"@{username}" if username else f"{first_name} (ID: {target_user_id})"
        admin_response = get_text('admin_withdrawal_confirm_success',
                                 user_mention=user_mention,
                                 amount=amount)
        
        await update.message.reply_text(admin_response, parse_mode='HTML')
        
        logger.info(f"Withdrawal WD-{request_id} completed for user {target_user_id}, amount Rp {amount:,.0f}")
        
    except Exception as e:
        logger.error(f"Gagal kirim konfirmasi penarikan ke user {target_user_id}: {e}")
        await update.message.reply_text(
            f"❌ <i>Gagal mengirim notifikasi ke user!</i>\n<code>Error: {str(e)}</code>",
            parse_mode='HTML'
        )
# ============================================================
# END OF ADMIN WITHDRAWAL CONFIRMATION HANDLER
# ============================================================

# ============================================================
# START OF BROADCAST SYSTEM HANDLERS
# ============================================================
async def handle_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk perintah /broadcast - khusus admin/owner
    
    Note: Untuk broadcast dengan gambar, gunakan caption yang dimulai dengan /broadcast
    CommandHandler hanya menangani pesan teks, bukan foto
    """
    user_id = update.effective_user.id
    
    # Validasi hanya owner yang bisa broadcast
    if user_id != OWNER_USER_ID:
        await update.message.reply_text(get_text('broadcast_admin_only'), parse_mode='HTML')
        return
    
    # Cek apakah ada pesan untuk broadcast
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(get_text('broadcast_usage'), parse_mode='HTML')
        return
    
    # Gabungkan argumen menjadi pesan
    broadcast_message = ' '.join(context.args)
    
    # Tampilkan konfirmasi
    await show_broadcast_confirmation(update, context, broadcast_message)

async def show_broadcast_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str, photo_file_id: str = None):
    """Tampilkan konfirmasi sebelum broadcast"""
    user_ids = get_all_user_ids()
    total_users = len(user_ids)
    
    if total_users == 0:
        await update.message.reply_text(get_text('broadcast_no_users'), parse_mode='HTML')
        return
    
    # Simpan data broadcast sementara
    context.user_data['broadcast_pending'] = {
        'message': message,
        'photo_file_id': photo_file_id,
        'total_users': total_users
    }
    
    confirm_text = get_text('broadcast_confirm', 
                           message=message[:500] + ('...' if len(message) > 500 else ''),
                           total_users=total_users)
    
    keyboard = [
        [InlineKeyboardButton("✅ Ya, Kirim Broadcast", callback_data="confirm_broadcast_yes")],
        [InlineKeyboardButton("❌ Batalkan", callback_data="confirm_broadcast_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if photo_file_id:
        await update.message.reply_photo(
            photo=photo_file_id,
            caption=confirm_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(confirm_text, reply_markup=reply_markup, parse_mode='HTML')

async def handle_broadcast_with_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk broadcast dengan gambar"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_USER_ID:
        await update.message.reply_text(get_text('broadcast_admin_only'), parse_mode='HTML')
        return
    
    caption = update.message.caption or ""
    
    # Hapus /broadcast dari caption
    if caption.startswith('/broadcast'):
        caption = caption[len('/broadcast'):].strip()
    
    if not caption:
        await update.message.reply_text(
            "❌ <i>Silakan tambahkan caption untuk broadcast dengan gambar.</i>\n\n"
            "<b>Contoh:</b> Kirim gambar dengan caption:\n"
            "<code>/broadcast 🎉 Promo Spesial Hari Ini!</code>",
            parse_mode='HTML'
        )
        return
    
    # Ambil file_id gambar (ukuran terbesar)
    photo_file_id = update.message.photo[-1].file_id
    
    # Tampilkan konfirmasi
    await show_broadcast_confirmation(update, context, caption, photo_file_id)

async def execute_broadcast(query, context: ContextTypes.DEFAULT_TYPE):
    """Eksekusi broadcast ke semua user"""
    import time
    
    broadcast_data = context.user_data.get('broadcast_pending')
    
    if not broadcast_data:
        try:
            await query.message.edit_text("❌ <i>Sesi broadcast berakhir. Silakan coba lagi.</i>", parse_mode='HTML')
        except:
            pass
        return
    
    message = broadcast_data['message']
    photo_file_id = broadcast_data.get('photo_file_id')
    total_users = broadcast_data['total_users']
    
    # Ambil semua user_id
    user_ids = get_all_user_ids()
    
    if len(user_ids) == 0:
        try:
            await query.message.edit_text(get_text('broadcast_no_users'), parse_mode='HTML')
        except:
            pass
        return
    
    # Update pesan dengan status "sedang mengirim"
    if photo_file_id:
        started_text = get_text('broadcast_with_image', message=message[:200] + ('...' if len(message) > 200 else ''), total_users=total_users)
    else:
        started_text = get_text('broadcast_started', message=message[:200] + ('...' if len(message) > 200 else ''), total_users=total_users)
    
    try:
        await query.message.edit_text(started_text, parse_mode='HTML')
    except:
        pass
    
    # Mulai broadcast
    start_time = time.time()
    success_count = 0
    failed_count = 0
    
    # Format pesan broadcast dengan header
    broadcast_content = f"📢 <b>PENGUMUMAN</b>\n\n{message}\n\n<i>— Tim @tukartonbot</i>"
    
    for target_user_id in user_ids:
        try:
            if photo_file_id:
                # Kirim dengan gambar
                await context.bot.send_photo(
                    chat_id=target_user_id,
                    photo=photo_file_id,
                    caption=broadcast_content,
                    parse_mode='HTML'
                )
            else:
                # Kirim teks saja
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=broadcast_content,
                    parse_mode='HTML'
                )
            success_count += 1
            
            # Delay untuk menghindari rate limit Telegram
            await asyncio.sleep(0.05)  # 50ms delay antara setiap pesan
            
        except Exception as e:
            failed_count += 1
            logger.warning(f"Failed to send broadcast to user {target_user_id}: {e}")
    
    end_time = time.time()
    duration = end_time - start_time
    
    # Simpan log broadcast
    admin_id = query.from_user.id
    save_broadcast_log(admin_id, message, len(user_ids), success_count, failed_count)
    
    # Update pesan dengan hasil
    completed_text = get_text('broadcast_completed',
                             message=message[:200] + ('...' if len(message) > 200 else ''),
                             total_users=len(user_ids),
                             success_count=success_count,
                             failed_count=failed_count,
                             duration=duration)
    
    try:
        await query.message.edit_text(completed_text, parse_mode='HTML')
    except:
        pass
    
    # Bersihkan data sementara
    context.user_data['broadcast_pending'] = None
    
    logger.info(f"Broadcast completed: {success_count}/{len(user_ids)} sent, {failed_count} failed, duration: {duration:.1f}s")

async def handle_broadcast_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handler callback untuk konfirmasi broadcast"""
    user_id = query.from_user.id
    
    # Validasi hanya owner
    if user_id != OWNER_USER_ID:
        await query.answer("⚠️ Hanya admin yang bisa melakukan broadcast", show_alert=True)
        return
    
    if query.data == "confirm_broadcast_yes":
        await query.answer("📢 Memulai broadcast...")
        await execute_broadcast(query, context)
    
    elif query.data == "confirm_broadcast_no":
        await query.answer("❌ Broadcast dibatalkan")
        context.user_data['broadcast_pending'] = None
        try:
            await query.message.edit_text(get_text('broadcast_cancelled'), parse_mode='HTML')
        except:
            pass
# ============================================================
# END OF BROADCAST SYSTEM HANDLERS
# ============================================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk error"""
    logger.error(f"Update {update} menyebabkan error {context.error}")

def main():
    """Fungsi utama untuk menjalankan bot"""
    
    print("=" * 50)
    print("🚀 TON Exchange Bot - VPS Version with Pagination")
    print("=" * 50)
    
    init_database()
    print("✅ Database initialized")
    
    print(f"Min TON: {MIN_TON}")
    print(f"Max Transaction: Rp {MAX_TRANSACTION_IDR:,}")
    print(f"Margin: Rp {MARGIN_PER_TON:,}")
    print(f"Admin: @{ADMIN_USERNAME}")
    print("=" * 50)
    
    if TELEGRAM_BOT_TOKEN == "MASUKKAN_TOKEN_BARU_ANDA_DI_SINI":
        print("❌ ERROR: Silakan ganti TELEGRAM_BOT_TOKEN dengan token bot Anda!")
        print("   Dapatkan token baru dari @BotFather di Telegram")
        return
    
    print("✅ Bot aktif...")
    print("=" * 50)
    
    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        # ============================================================
        # START OF BROADCAST COMMAND HANDLER REGISTRATION
        # ============================================================
        application.add_handler(CommandHandler("broadcast", handle_broadcast_command))
        # Handler untuk broadcast dengan gambar (caption dimulai dengan /broadcast)
        application.add_handler(MessageHandler(
            filters.PHOTO & filters.CaptionRegex(r'^/broadcast'),
            handle_broadcast_with_image
        ))
        # ============================================================
        # END OF BROADCAST COMMAND HANDLER REGISTRATION
        # ============================================================
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        # Handler untuk foto (selain broadcast dengan caption) - untuk bukti transfer
        application.add_handler(MessageHandler(filters.PHOTO & ~filters.CaptionRegex(r'^/broadcast'), handle_message))
        application.add_error_handler(error_handler)
        
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        logger.error(f"Bot error: {e}", exc_info=True)

if __name__ == '__main__':
    main()

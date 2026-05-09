import socket
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
import struct
import datetime
import os

#------------------------------------------------------------
# کلاس مدیریت رمزنگاری (قابل تنظیم با کلید پویا)
class Crypto:
    def __init__(self, key: bytes):
        self.key = key

    def encrypt(self, data: bytes) -> bytes:
        return bytes(b ^ self.key[i % len(self.key)] for i, b in enumerate(data))

    def decrypt(self, data: bytes) -> bytes:
        return self.encrypt(data)   # XOR متقارن
#------------------------------------------------------------

class VPNServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("VPN Server - Advanced Edition")
        self.root.geometry("800x600")
        self.server_running = False
        self.server_socket = None
        self.server_thread = None
        self.clients = {}          # mapping client_socket -> (addr, thread, crypto)
        self.crypto = None         # ساخته می‌شود بعد از دریافت کلید

        # ================== قاب تنظیمات اصلی ==================
        main_frame = ttk.LabelFrame(root, text="Server Settings", padding=5)
        main_frame.pack(fill="x", padx=5, pady=5)

        # سطر 0: Host و Port
        ttk.Label(main_frame, text="Listen Host:").grid(row=0, column=0, sticky="e", padx=2)
        self.host_entry = ttk.Entry(main_frame, width=20)
        self.host_entry.insert(0, "0.0.0.0")
        self.host_entry.grid(row=0, column=1, padx=2, pady=2)

        ttk.Label(main_frame, text="Port:").grid(row=0, column=2, sticky="e", padx=2)
        self.port_entry = ttk.Entry(main_frame, width=10)
        self.port_entry.insert(0, "9000")
        self.port_entry.grid(row=0, column=3, padx=2, pady=2)

        # سطر 1: Secret Key
        ttk.Label(main_frame, text="Encryption Key:").grid(row=1, column=0, sticky="e", padx=2)
        self.key_entry = ttk.Entry(main_frame, width=40, show="*")
        self.key_entry.insert(0, "my_secret_key_16b")
        self.key_entry.grid(row=1, column=1, columnspan=3, sticky="w", padx=2, pady=2)

        # سطر 2: Timeout و Buffer Size
        ttk.Label(main_frame, text="Connection Timeout (sec):").grid(row=2, column=0, sticky="e", padx=2)
        self.timeout_entry = ttk.Entry(main_frame, width=10)
        self.timeout_entry.insert(0, "5")
        self.timeout_entry.grid(row=2, column=1, sticky="w", padx=2, pady=2)

        ttk.Label(main_frame, text="Recv Buffer (bytes):").grid(row=2, column=2, sticky="e", padx=2)
        self.buffer_entry = ttk.Entry(main_frame, width=10)
        self.buffer_entry.insert(0, "8192")
        self.buffer_entry.grid(row=2, column=3, sticky="w", padx=2, pady=2)

        # سطر 3: Max Connections و گزینه Log to File
        ttk.Label(main_frame, text="Max Clients:").grid(row=3, column=0, sticky="e", padx=2)
        self.max_clients_entry = ttk.Entry(main_frame, width=10)
        self.max_clients_entry.insert(0, "20")
        self.max_clients_entry.grid(row=3, column=1, sticky="w", padx=2, pady=2)

        self.log_to_file_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(main_frame, text="Save log to file", variable=self.log_to_file_var).grid(row=3, column=2, columnspan=2, sticky="w", padx=2)

        # دکمه‌های Start / Stop
        self.start_btn = ttk.Button(main_frame, text="▶ Start Server", command=self.start_server)
        self.start_btn.grid(row=4, column=0, pady=8, padx=2)

        self.stop_btn = ttk.Button(main_frame, text="⏹ Stop Server", command=self.stop_server, state=tk.DISABLED)
        self.stop_btn.grid(row=4, column=1, pady=8, padx=2)

        # ================== نمایش کلاینت‌های متصل ==================
        client_frame = ttk.LabelFrame(root, text="Connected Clients", padding=5)
        client_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.client_listbox = tk.Listbox(client_frame, height=6)
        self.client_listbox.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(client_frame, orient="vertical", command=self.client_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.client_listbox.config(yscrollcommand=scrollbar.set)

        btn_frame = ttk.Frame(client_frame)
        btn_frame.pack(side="bottom", fill="x", pady=2)
        ttk.Button(btn_frame, text="Kick Selected Client", command=self.kick_client).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Refresh List", command=self.refresh_client_list).pack(side="left", padx=2)

        # ================== ناحیه لاگ ==================
        log_frame = ttk.LabelFrame(root, text="Log", padding=5)
        log_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.log_area = scrolledtext.ScrolledText(log_frame, width=80, height=12, state='normal')
        self.log_area.pack(fill="both", expand=True)

        # ================== نوار وضعیت ==================
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(root, textvariable=self.status_var, relief="sunken", anchor="w")
        status_bar.pack(side="bottom", fill="x")

        self.log_file = None

    # ------------------------------------------------------------
    def log(self, msg, level="INFO"):
        """اضافه کردن پیام با تایم‌استمپ و optionally ذخیره در فایل"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted = f"[{timestamp}] [{level}] {msg}"
        self.log_area.insert(tk.END, formatted + "\n")
        self.log_area.see(tk.END)
        self.root.update_idletasks()

        if self.log_to_file_var.get():
            if self.log_file is None:
                try:
                    log_filename = f"vpn_server_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                    self.log_file = open(log_filename, "a", encoding="utf-8")
                except Exception as e:
                    messagebox.showerror("Log Error", f"Cannot open log file: {e}")
                    return
            self.log_file.write(formatted + "\n")
            self.log_file.flush()

    # ------------------------------------------------------------
    def update_status(self, text):
        self.status_var.set(text)

    # ------------------------------------------------------------
    def refresh_client_list(self):
        """به‌روزرسانی لیست کلاینت‌های متصل در GUI"""
        self.client_listbox.delete(0, tk.END)
        for sock, (addr, _, _) in self.clients.items():
            self.client_listbox.insert(tk.END, f"{addr[0]}:{addr[1]}")
        if not self.clients:
            self.client_listbox.insert(tk.END, "(no clients)")

    # ------------------------------------------------------------
    def kick_client(self):
        """قطع اتصال کلاینت انتخاب شده"""
        selection = self.client_listbox.curselection()
        if not selection:
            messagebox.showinfo("Kick", "No client selected")
            return
        client_str = self.client_listbox.get(selection[0])
        if client_str == "(no clients)":
            return
        # پیدا کردن سوکت مربوطه
        for sock, (addr, thread, crypto) in list(self.clients.items()):
            if f"{addr[0]}:{addr[1]}" == client_str:
                try:
                    sock.close()
                except:
                    pass
                self.log(f"Client {client_str} kicked by admin", "WARNING")
                # حذف از دیکشنری بعداً توسط handle_client انجام می‌شود
                break
        self.refresh_client_list()

    # ------------------------------------------------------------
    def start_server(self):
        if self.server_running:
            return
        # دریافت تنظیمات
        try:
            host = self.host_entry.get().strip()
            port = int(self.port_entry.get())
            timeout_val = int(self.timeout_entry.get())
            buffer_size = int(self.buffer_entry.get())
            max_clients = int(self.max_clients_entry.get())
            key = self.key_entry.get().strip().encode()
            if not key:
                raise ValueError("Encryption key cannot be empty")
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid setting: {e}")
            return

        self.crypto = Crypto(key)
        self.timeout_val = timeout_val
        self.buffer_size = buffer_size
        self.max_clients = max_clients

        self.server_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.update_status("Starting server...")
        self.log(f"Starting server on {host}:{port} (key={key[:3]}***, timeout={timeout_val}s, buffer={buffer_size}, max={max_clients})")

        # اجرای سرور در یک نخ جداگانه
        self.server_thread = threading.Thread(target=self.run_server, args=(host, port), daemon=True)
        self.server_thread.start()

    # ------------------------------------------------------------
    def run_server(self, host, port):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((host, port))
            self.server_socket.listen(self.max_clients)
            self.server_socket.settimeout(1)
            self.log(f"Server is listening on {host}:{port}")
            self.update_status("Server running")

            while self.server_running:
                try:
                    client_sock, addr = self.server_socket.accept()
                    # بررسی محدودیت تعداد کلاینت
                    if len(self.clients) >= self.max_clients:
                        self.log(f"Rejected connection from {addr[0]}:{addr[1]} (max clients reached)", "WARNING")
                        client_sock.close()
                        continue
                    self.log(f"New connection from {addr[0]}:{addr[1]}")
                    # هر کلاینت در نخ مجزا
                    client_thread = threading.Thread(target=self.handle_client, args=(client_sock, addr), daemon=True)
                    self.clients[client_sock] = (addr, client_thread, self.crypto)
                    client_thread.start()
                    self.root.after(0, self.refresh_client_list)
                except socket.timeout:
                    continue
                except OSError:
                    break
        except Exception as e:
            self.log(f"Server error: {e}", "ERROR")
        finally:
            self.server_running = False
            # بستن تمام کلاینت‌های باقی‌مانده
            for sock in list(self.clients.keys()):
                try:
                    sock.close()
                except:
                    pass
            self.clients.clear()
            if self.server_socket:
                try:
                    self.server_socket.close()
                except:
                    pass
            self.log("Server stopped.")
            self.update_status("Stopped")
            self.root.after(0, self._enable_start_button)
            self.root.after(0, self.refresh_client_list)

    # ------------------------------------------------------------
    def _enable_start_button(self):
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    # ------------------------------------------------------------
    def handle_client(self, client_sock, addr):
        crypto = self.clients.get(client_sock, (None, None, None))[2]
        if not crypto:
            return
        try:
            # 1. دریافت طول داده رمز شده
            raw_len = client_sock.recv(4)
            if len(raw_len) != 4:
                self.log(f"Client {addr[0]}:{addr[1]} - Invalid length header", "WARNING")
                return
            data_len = struct.unpack('!I', raw_len)[0]
            if data_len > 10 * 1024 * 1024:  # حداکثر 10 مگابایت
                self.log(f"Client {addr[0]}:{addr[1]} - Payload too large ({data_len})", "ERROR")
                return
            data = b''
            while len(data) < data_len:
                chunk = client_sock.recv(min(4096, data_len - len(data)))
                if not chunk:
                    return
                data += chunk
            # رمزگشایی
            decrypted = crypto.decrypt(data)

            # جدا کردن host:port از payload
            separator = decrypted.find(b'|')
            if separator == -1:
                self.log(f"Client {addr[0]}:{addr[1]} - Invalid format (missing '|')", "WARNING")
                return
            host_port = decrypted[:separator].decode()
            payload = decrypted[separator+1:]

            host, port = host_port.split(':')
            port = int(port)
            self.log(f"Client {addr[0]}:{addr[1]} requests {host}:{port}")

            # اتصال به مقصد نهایی
            remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            remote.settimeout(self.timeout_val)
            remote.connect((host, port))
            remote.sendall(payload)

            # دریافت پاسخ
            response = b''
            remote.settimeout(self.timeout_val)
            try:
                while True:
                    chunk = remote.recv(self.buffer_size)
                    if not chunk:
                        break
                    response += chunk
            except socket.timeout:
                pass
            remote.close()

            # ارسال پاسخ رمز شده به کلاینت
            encrypted_resp = crypto.encrypt(response)
            client_sock.sendall(struct.pack('!I', len(encrypted_resp)) + encrypted_resp)
            self.log(f"Client {addr[0]}:{addr[1]} - Sent {len(response)} bytes back")

        except ConnectionRefusedError:
            self.log(f"Client {addr[0]}:{addr[1]} - Connection refused by {host}:{port}", "ERROR")
        except socket.timeout:
            self.log(f"Client {addr[0]}:{addr[1]} - Timeout connecting to {host}:{port}", "ERROR")
        except Exception as e:
            self.log(f"Error handling client {addr[0]}:{addr[1]}: {e}", "ERROR")
        finally:
            try:
                client_sock.close()
            except:
                pass
            # حذف از دیکشنری کلاینت‌ها
            if client_sock in self.clients:
                del self.clients[client_sock]
            self.root.after(0, self.refresh_client_list)

    # ------------------------------------------------------------
    def stop_server(self):
        if not self.server_running:
            return
        self.log("Stopping server...", "WARNING")
        self.server_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        # بستن فایل لاگ در صورت باز بودن
        if self.log_file:
            self.log_file.close()
            self.log_file = None
        self.update_status("Stopping...")

    # ------------------------------------------------------------
    def __del__(self):
        if self.log_file:
            self.log_file.close()

# ------------------------------------------------------------
if __name__ == "__main__":
    root = tk.Tk()
    app = VPNServerGUI(root)
    root.mainloop()

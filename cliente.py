import socket
import threading
import json
import time
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
from datetime import datetime
import sqlite3
HOST = 'localhost'
PORT = 8000

class ChatClientLogic:
    """
    Lida com a lógica principal para o cliente de chat, incluindo comunicação de rede, 
    envio/recebimento de mensagens, autenticação e gerenciamento da lista de usuários.
    """
    def __init__(self):
        self.socket = None
        self.username = None
        self.connected = False
        self.last_typing_time = 0
        self.response_received = threading.Event()
        self.login_status = None
        self.gui_callback = None

    def connect(self):
        """Estabelece uma nova conexão com o servidor."""

        if self.connected and self.socket is not None:
            return True

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        try:
            sock.connect((HOST, PORT))

            self.socket = sock
            self.connected = True

            threading.Thread(
                target=self.receive_messages,
                args=(sock,),
                daemon=True
            ).start()

            print(
                f"[ClientLogic] Conectado ao servidor em {HOST}:{PORT}"
            )

            return True

        except OSError as erro:
            try:
                sock.close()
            except OSError:
                pass

            self.socket = None
            self.connected = False

            print(
                f"[ClientLogic] Erro de conexão ao servidor: {erro}"
            )

            if self.gui_callback:
                self.gui_callback({
                    'type': 'connection_error',
                    'message': str(erro)
                })

            return False

    def _send_json_message(self, message):
        """Método auxiliar para serializar um dicionário em JSON e enviá-lo pelo socket."""
        if not self.connected or not self.socket:
            print("[ClientLogic] Não conectado para enviar mensagem.")
            return False
        try:
            message_str = json.dumps(message) + '\n'
            self.socket.send(message_str.encode('utf-8'))
            return True
        except Exception as e:
            self.connected = False
            print(f"[ClientLogic] Erro ao enviar JSON para o servidor: {e}")
            if self.gui_callback:
                self.gui_callback({'type': 'server_disconnect', 'message': "Erro de comunicação. Conexão perdida."})
            return False

    def register(self, username, password):
        """Solicita o cadastro ao servidor."""

        if not self.connected and not self.connect():
            return False

        message = {
            'type': 'register',
            'username': username,
            'password': password
        }

        self.login_status = None
        self.response_received.clear()

        if not self._send_json_message(message):
            return False

        if not self.response_received.wait(10):
            print(
                "[ClientLogic] Tempo esgotado aguardando resposta do cadastro."
            )
            return False

        return self.login_status is True

    def login(self, username, password):
        if not self.connected or self.socket is None:
            print("Cliente não conectado ao servidor.")
            return False

        self.response_received.clear()
        self.login_status = None

        mensagem = {
            "type": "login",
            "username": username,
            "password": password
        }

        if not self._send_json_message(mensagem):
            return False

        recebido = self.response_received.wait(timeout=5)

        if not recebido:
            print("Tempo esgotado aguardando resposta do servidor.")
            return False

        return self.login_status

    def logout(self):
        """Envia uma solicitação de logout para o servidor e limpa o estado."""
        if self.username and self.connected:
            message = {'type': 'logout'}
            self._send_json_message(message)
        
        self.username = None
        self.connected = False
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            finally:
                self.socket.close()
                self.socket = None
        print("[ClientLogic] Desconectado do servidor.")

    
    def send_message(self, receiver, content):
    #Envia uma mensagem para um usuário específico ou para todos.

        if not self.username or not self.connected:
            if self.gui_callback:
                self.gui_callback({
                    'type': 'message_error',
                    'message': 'Você precisa estar logado para enviar mensagens.'
                })
            return False

        if not receiver or not content.strip():
            if self.gui_callback:
                self.gui_callback({
                    'type': 'message_error',
                    'message': 'Informe o destinatário e uma mensagem.'
                })
            return False

        message = {
            'type': 'message',
            'sender': self.username,
            'receiver': receiver,
            'content': content.strip(),
            'timestamp': datetime.now().strftime('%H:%M:%S')
        }

        try:
            return self._send_json_message(message)

        except (OSError, AttributeError) as erro:
            print(f"[ClientLogic] Falha ao enviar mensagem: {erro}")

            self.connected = False

            if self.gui_callback:
                self.gui_callback({
                    'type': 'message_error',
                    'message': 'A conexão foi encerrada. Reconecte-se ao servidor.'
                })

            return False



    def start_typing(self, recipient):
        if not self.username or not self.connected:
            return
        message = {'type': 'typing', 'username': self.username, 'recipient': recipient}
        self._send_json_message(message)

    def stop_typing(self, recipient):
        if not self.username or not self.connected:
            return
        message = {'type': 'stop_typing', 'username': self.username, 'recipient': recipient}
        self._send_json_message(message)

    def get_user_list(self):
        if not self.username or not self.connected:
            return
        message = {'type': 'get_users'}
        self._send_json_message(message)

    def receive_messages(self, sock):
        """Recebe mensagens utilizando o socket desta conexão."""

        buffer = ""

        try:
            while self.connected and self.socket is sock:

                data = sock.recv(4096)

                if not data:
                    print(
                        "[ClientLogic] Servidor encerrou a conexão."
                    )
                    break

                buffer += data.decode("utf-8")

                while "\n" in buffer:
                    message_str, buffer = buffer.split("\n", 1)

                    if not message_str.strip():
                        continue

                    try:
                        message = json.loads(message_str)

                        # Processar respostas de login e cadastro
                        if message.get("type") in [
                            "login_response",
                            "register_response"
                        ]:
                            self.login_status = (
                                message.get("status") == "success"
                            )
                            if (message.get('type') == 'login_response' 
                                and self.login_status
                            ): 
                                self.username = message.get('username')

                            self.response_received.set()

                        # Encaminhar a mensagem para a interface
                        if self.gui_callback:
                            self.gui_callback(message)

                    except json.JSONDecodeError as erro:
                        print(
                            f"[ClientLogic] Erro ao interpretar JSON: {erro}"
                        )

        except OSError as erro:
            # Uma conexão antiga pode ser encerrada durante o logout.
            # Não trate esse encerramento esperado como falha do servidor.
            if self.socket is sock and self.connected:
                print(
                    f"[ClientLogic] Erro na recepção: {erro}"
                )

        finally:
            try:
                sock.close()
            except OSError:
                pass

            # Somente a thread da conexão atual pode limpar seu estado.
            if self.socket is sock:
                self.socket = None
                self.connected = False

                if self.gui_callback:
                    self.gui_callback({
                        'type': 'server_disconnect',
                        'message': 'A conexão com o servidor foi encerrada.'
                    })


class ChatAppGUI:
    """Gerencia a interface gráfica do aplicativo de chat."""
    def __init__(self, master):
        self.master = master
        self.master.title("Bem vindo ao Chat")
        self.master.geometry("1000x700")
        self.master.minsize(800, 600)
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.style.configure('TFrame', background="#133c47")
        self.style.configure('TLabel', background="#133c47", font=("Arial", 11))
        self.style.configure('TButton', font=("Arial", 11, "bold"), padding=8)

        self.client_logic = ChatClientLogic()
        self.client_logic.gui_callback = self.handle_server_message
        self.current_chat_with = "all"

        self.chat_history = {"all": []}
        self.unread_messages = {}
        self.typing_timer = None

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.message_input_var = tk.StringVar()
        self.info_message_var = tk.StringVar()

        self.setup_login_screen()
        threading.Thread(target=self.client_logic.connect, daemon=True).start()

    def clear_frame(self):
        for widget in self.master.winfo_children():
            widget.destroy()

    def setup_login_screen(self):
        self.clear_frame()
        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_columnconfigure(0, weight=1)

        self.login_frame = ttk.Frame(self.master, padding="40 20 40 20", relief="raised")
        self.login_frame.grid(row=0, column=0, padx=50, pady=50, sticky="nsew")
        self.login_frame.grid_rowconfigure((0,1,2,3,4,5), weight=1)
        self.login_frame.grid_columnconfigure((0,1), weight=1)

        ttk.Label(self.login_frame, text="Bem vindo ao Chat", font=("Arial", 30, "bold"), foreground="#007bff").grid(row=0, column=0, columnspan=2, pady=20)

        ttk.Label(self.login_frame, text="Usuário:", font=("Arial", 14)).grid(row=1, column=0, sticky="e", pady=5, padx=10)
        self.username_entry = ttk.Entry(self.login_frame, textvariable=self.username_var, width=30, font=("Arial", 14))
        self.username_entry.grid(row=1, column=1, sticky="w", pady=5, padx=10)
        self.username_entry.focus_set()

        ttk.Label(self.login_frame, text="Senha:", font=("Arial", 14)).grid(row=2, column=0, sticky="e", pady=5, padx=10)
        self.password_entry = ttk.Entry(self.login_frame, textvariable=self.password_var, show="*", width=30, font=("Arial", 14))
        self.password_entry.grid(row=2, column=1, sticky="w", pady=5, padx=10)

        button_frame = ttk.Frame(self.login_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=20)
        
        ttk.Button(button_frame, text="Entrar", command=self.login_user, style='Login.TButton').grid(row=0, column=0, padx=10)
        ttk.Button(button_frame, text="Registrar-se", command=self.register_user, style='Register.TButton').grid(row=0, column=1, padx=10)
        
        self.style.configure('Login.TButton', background='#1a8dff', foreground='white')
        self.style.configure('Register.TButton', background='#28a745', foreground='white')

        self.status_label = ttk.Label(self.login_frame, text="", font=("Arial", 12, "italic"), foreground="red")
        self.status_label.grid(row=4, column=0, columnspan=2, pady=10)
        
        self.connection_status_label = ttk.Label(self.login_frame, text="Conectando ao servidor...", font=("Arial", 10), foreground="gray")
        self.connection_status_label.grid(row=5, column=0, columnspan=2, pady=5)

    def update_connection_status(self, message, color="gray"):
        if hasattr(self, 'connection_status_label') and self.connection_status_label.winfo_exists():
            self.connection_status_label.config(text=message, foreground=color)

    def login_user(self):
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()

        if not username or not password:
            self.status_label.config(text="Preencha usuário e senha.", foreground="red")
            return

        if not self.client_logic.connected:
            if not self.client_logic.connect():
                self.status_label.config(text="Erro de conexão com o servidor.", foreground="red")
                return

        self.status_label.config(text="Entrando...", foreground="blue")
        threading.Thread(target=self._perform_login, args=(username, password), daemon=True).start()

    def _perform_login(self, username, password):
        success = self.client_logic.login(username, password)
        self.master.after(0, lambda: self._handle_login_response(success, username))

    def _perform_register(self, username, password):
        sucesso = self.client_logic.register(username, password)

        self.master.after(
            0,
            lambda: self._handle_register_response(sucesso)
        )

    def _handle_register_response(self, success):
        if success:
            self.status_label.config(
                text="Cadastro realizado! Faça login.",
                foreground="green"
            )
            self.password_var.set("")
        else:
            self.status_label.config(
                text="Falha no cadastro. Verifique os dados.",
                foreground="red"
            )
    def _handle_login_response(self, success, username): 
        if success: 
            self.client_logic.username = username 
            self.username_var.set(username) 
        
            self.status_label.config( 
                text="Login realizado com sucesso!", 
                foreground="green" ) # Abrir a interface principal do chat 
            self.setup_main_chat_screen() # Solicitar a lista de usuários conectados 
            self.client_logic.get_user_list() 
        else: 
            self.status_label.config(
                 text="Usuário ou senha incorretos.", 
                 foreground="red" )
               
    def register_user(self):
        """Obtém os dados e solicita o cadastro ao servidor."""

        username = self.username_var.get().strip()
        password = self.password_var.get()

        if not username or not password:
            self.status_label.config(
                text="Preencha o usuário e a senha.",
                foreground="red"
            )
            return

        if not self.client_logic.connected:
            if not self.client_logic.connect():
                self.status_label.config(
                    text="Não foi possível conectar ao servidor.",
                    foreground="red"
                )
                return

        self.status_label.config(
            text="Realizando cadastro...",
            foreground="blue"
        )

        threading.Thread(
            target=self._perform_register,
            args=(username, password),
            daemon=True
        ).start()

        def _perform_register(self, username, password):
            success = self.client_logic.register(username, password)
            self.master.after(0, lambda: self._handle_register_response(success))

        def _handle_register_response(self, success):
            if success:
                self.status_label.config(text="Registro realizado com sucesso! Faça login.", foreground="green")
                self.password_var.set("")
            else:
                self.status_label.config(text="Falha no registro (usuário já existe?).", foreground="red")

    def setup_main_chat_screen(self):
        self.clear_frame()

        self.master.grid_rowconfigure(0, weight=1)
        self.master.grid_rowconfigure(1, weight=0)
        self.master.grid_columnconfigure(0, weight=0)
        self.master.grid_columnconfigure(1, weight=1)

        self.main_frame = ttk.Frame(self.master, padding=10)
        self.main_frame.grid(row=0, column=0, columnspan=2, sticky="nsew")
        
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=0)
        self.main_frame.grid_rowconfigure(2, weight=0)
        self.main_frame.grid_columnconfigure(0, weight=0)
        self.main_frame.grid_columnconfigure(1, weight=1)

        # User List Frame
        self.user_list_frame = ttk.Frame(self.main_frame, width=250, relief="groove", borderwidth=2)
        self.user_list_frame.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=(0, 10))
        self.user_list_frame.grid_propagate(False)
        self.user_list_frame.grid_rowconfigure(1, weight=1)
        self.user_list_frame.grid_columnconfigure(0, weight=1)

        ttk.Label(self.user_list_frame, text="Contatos", font=("Arial", 13, "bold"), anchor="center", background="#688996").grid(row=0, column=0, pady=5, sticky="ew")
        
        # ÚNICA criação correta da Listbox de usuários
        self.user_listbox = tk.Listbox(self.user_list_frame, font=("Arial", 12), selectmode=tk.SINGLE, 
                                       bg="#ffffff", fg="#333333", selectbackground="#007bff", selectforeground="white")
        self.user_listbox.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.user_listbox.bind('<<ListboxSelect>>', self.on_user_select)

        # Chat Area Frame
        self.chat_area_frame = ttk.Frame(self.main_frame, relief="groove", borderwidth=2)
        self.chat_area_frame.grid(row=0, column=1, rowspan=3, sticky="nsew", padx=(10, 0))
        self.chat_area_frame.grid_rowconfigure(1, weight=1)
        self.chat_area_frame.grid_columnconfigure(0, weight=1)

        self.chat_title_label = ttk.Label(self.chat_area_frame, text="Chat Público", font=("Arial", 14, "bold"), foreground="#007bff", background="#141f24")
        self.chat_title_label.grid(row=0, column=0, sticky="ew", pady=(5,0), padx=5)

        self.chat_display = scrolledtext.ScrolledText(self.chat_area_frame, state='disabled', font=("Consolas", 11), wrap=tk.WORD, bg="#f8f8f8")
        self.chat_display.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        self.chat_display.tag_config('sent', foreground='#0056b3', font=("Consolas", 11, "bold"))
        self.chat_display.tag_config('received', foreground='#333333')
        self.chat_display.tag_config('system', foreground='#8b0000', font=("Consolas", 10, "italic"))
        self.chat_display.tag_config('timestamp', foreground='gray', font=("Consolas", 9))

        self.message_input_frame = ttk.Frame(self.chat_area_frame)
        self.message_input_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        self.message_input_frame.grid_columnconfigure(0, weight=1)

        self.message_entry = ttk.Entry(self.message_input_frame, textvariable=self.message_input_var, font=("Arial", 12))
        self.message_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.message_entry.bind('<Return>', self.send_chat_message)
        self.message_input_var.trace_add("write", self.check_send_button_state)

        self.send_button = ttk.Button(self.message_input_frame, text="Enviar", command=self.send_chat_message)
        self.send_button.grid(row=0, column=1, sticky="e")
        self.send_button.state(['disabled'])

        ttk.Button(self.master, text="Sair do Chat", command=self.logout_user).grid(row=1, column=0, columnspan=2, pady=10)

        self.load_current_chat_history_to_display()

    def check_send_button_state(self, *args):
        if hasattr(self, 'send_button') and self.send_button.winfo_exists():
            if self.message_input_var.get().strip():
                self.send_button.state(['!disabled'])
            else:
                self.send_button.state(['disabled'])

    def append_message_to_display(self, message_parts):
        self.chat_display.config(state='normal')
        for text, tag in message_parts:
            self.chat_display.insert(tk.END, text, tag)
        self.chat_display.insert(tk.END, "\n")
        self.chat_display.yview(tk.END)
        self.chat_display.config(state='disabled')

    def clear_chat_area(self):
        self.chat_display.config(state='normal')
        self.chat_display.delete(1.0, tk.END)
        self.chat_display.config(state='disabled')
    
    def load_current_chat_history_to_display(self):
        self.clear_chat_area()
        if self.current_chat_with in self.chat_history:
            for msg_parts in self.chat_history[self.current_chat_with]:
                self.append_message_to_display(msg_parts)

    def update_user_list_gui(self, users_data):
        # Verifica se o widget da lista de usuários existe na tela atual
        if not hasattr(self, 'user_listbox') or not self.user_listbox.winfo_exists():
            return

        self.user_listbox.delete(0, tk.END)
        
        # Adiciona fixo o Chat Público no topo
        self.user_listbox.insert(tk.END, "Chat Público")

        for user_info in sorted(users_data, key=lambda x: x['username'].lower()):
            username = user_info['username']
            status = user_info['status']
            if username != self.client_logic.username:
                self.user_listbox.insert(tk.END, f"{username} ({status})")
                if username not in self.chat_history:
                    self.chat_history[username] = []
                if username not in self.unread_messages:
                    self.unread_messages[username] = False

    def on_user_select(self, event=None):
        selected_indices = self.user_listbox.curselection()
        if not selected_indices:
            return
        
        index = selected_indices[0]
        selected_text = self.user_listbox.get(index)

        if "Chat Público" in selected_text:
            new_partner = "all"
        else:
            new_partner = selected_text.split(' ')[0]

        if self.current_chat_with != new_partner:
            self.current_chat_with = new_partner
            title = "Chat Público" if new_partner == "all" else f"Chat com {new_partner}"
            if hasattr(self, 'chat_title_label') and self.chat_title_label.winfo_exists():
                self.chat_title_label.config(text=title)
            self.load_current_chat_history_to_display()

    def send_chat_message(self, event=None):
        content = self.message_input_var.get().strip()
        if not content:
            return

        receiver = self.current_chat_with
        success = self.client_logic.send_message(receiver, content)
        if success:
            timestamp = datetime.now().strftime('%H:%M:%S')
            msg_parts = [
                (f"[{timestamp}] ", 'timestamp'),
                ("Você: ", 'sent'),
                (content, 'received')
            ]
            self.chat_history[receiver].append(msg_parts)
            if receiver == self.current_chat_with:
                self.append_message_to_display(msg_parts)
            self.message_input_var.set("")

    def handle_server_message(self, message):
        msg_type = message.get('type')
        
        if msg_type == 'user_list':
            self.master.after(0, lambda: self.update_user_list_gui(message.get('users', [])))
        
        elif msg_type == 'message':
            sender = message.get('sender')
            receiver = message.get('receiver')
            content = message.get('content')
            timestamp = message.get('timestamp', datetime.now().strftime('%H:%M:%S'))
            
            # Se for privado, a chave do histórico é o sender; se for público ('all'), é 'all'
            target_chat = 'all' if receiver == 'all' else sender

            if target_chat not in self.chat_history:
                self.chat_history[target_chat] = []

            msg_parts = [
                (f"[{timestamp}] ", 'timestamp'),
                (f"{sender}: ", 'sender'),
                (content, 'received')
            ]
            
            self.chat_history[target_chat].append(msg_parts)
            
            if self.current_chat_with == target_chat:
                self.master.after(0, lambda: self.append_message_to_display(msg_parts))

        elif msg_type == 'server_disconnect':
            self.master.after(0, lambda: messagebox.showerror("Desconectado", message.get('message', "Conexão perdida")))
            self.master.after(0, self.setup_login_screen)

    def logout_user(self):
        self.client_logic.logout()
        self.setup_login_screen()

    def on_closing(self):
        if messagebox.askokcancel("Sair", "Deseja realmente sair do chat?"):
            self.client_logic.logout()
            self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = ChatAppGUI(root)
    root.mainloop()

import socket
import threading
import time

class HandleClient:
    def __init__(self):
        self.sock = None
        self.connected = False
        self.cmd_handlers = []
        self.chg_handlers = []
        self._stop_event = threading.Event()
        self.receive_thread = None

    def append_cmd_handler(self, handler):
        self.cmd_handlers.append(handler)

    def append_chg_handler(self, handler):
        self.chg_handlers.append(handler)

    def connect(self, host, port):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((host, port))
            self.connected = True
            self._notify_status_change()
            
            # Start receive thread
            self._stop_event.clear()
            self.receive_thread = threading.Thread(target=self._receive_loop)
            self.receive_thread.daemon = True
            self.receive_thread.start()
            return True
        except Exception as e:
            print(f"Connection error: {e}")
            self.connected = False
            return False

    def close(self):
        self.connected = False
        self._stop_event.set()
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        self._notify_status_change()

    def _notify_status_change(self):
        for h in self.chg_handlers:
            try:
                h()
            except Exception as e:
                print(f"Error in status handler: {e}")

    def _receive_loop(self):
        buffer = ""
        while not self._stop_event.is_set() and self.connected:
            try:
                data = self.sock.recv(4096)
                if not data:
                    break
                
                text = data.decode('utf-8')
                buffer += text
                
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    if line:
                        self._process_command(line)
                        
            except Exception as e:
                # print(f"Receive error: {e}")
                break
        
        self.connected = False
        self._notify_status_change()

    def _process_command(self, line):
        # Protocol: parameters separated by semicolon? 
        # Or maybe the responses are different?
        # PDF says "Os parâmetros são separados utilizando o símbolo ponto e virgula (“;”)."
        # Bot.py expects cmd as a list where cmd[0] is the command.
        # So "o;blocked" -> ["o", "blocked"]?
        # Or "notification;bla" -> ["notification", "bla"]
        
        parts = line.split(';')
        # Clean parts
        parts = [p.strip() for p in parts]
        
        for h in self.cmd_handlers:
            try:
                h(parts)
            except Exception as e:
                print(f"Error in cmd handler: {e}")

    def _send(self, msg):
        if self.connected and self.sock:
            try:
                self.sock.sendall((msg + "\n").encode('utf-8'))
            except Exception as e:
                print(f"Send error: {e}")
                self.close()

    # Commands from PDF
    def sendForward(self): self._send("w")
    def sendBackward(self): self._send("s")
    def sendTurnLeft(self): self._send("a")
    def sendTurnRight(self): self._send("d")
    def sendGetItem(self): self._send("t")
    def sendShoot(self): self._send("e")
    def sendRequestObservation(self): self._send("o")
    def sendRequestGameStatus(self): self._send("g")
    def sendRequestUserStatus(self): self._send("q")
    def sendRequestPosition(self): self._send("p")
    def sendRequestScoreboard(self): self._send("u")
    def sendGoodbye(self): self._send("quit")
    
    def sendName(self, name): self._send(f"name;{name}")
    def sendSay(self, msg): self._send(f"say;{msg}")
    def sendRGB(self, r, g, b): self._send(f"color;{r};{g};{b}")

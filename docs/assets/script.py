from pwn import *
import paramiko

host = "192.168.1.130"
username = "joperpu"
password = "prueba"
attempts = 0

while attempts < 10:
    try:
        response = ssh(host=host, user=username, password=password, timeout=1)
        if not response.connect():
            print("Intento realizado")
        response.close()
    except paramiko.ssh_exception.AuthenticationException:
        print("Contraseña incorrecta")
    
    attempts+=1
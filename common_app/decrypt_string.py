import hashlib
import base64
from Crypto.Cipher import AES

class DecryptString:
    @staticmethod
    def md5(input_string):
        return hashlib.md5(input_string.encode()).hexdigest()

    @staticmethod
    def set_enc_dec_user(data, act, flag):
        secret_key = "]d=3T[N}+:}YiA;cv418j*dCs"
        initial_vector_string = "9eQV5B41wgCyqQb9"
        if data is not None:
            try:
                if flag == "":
                    return str(data).replace("$", "")
                else:
                    key = DecryptString.md5(secret_key).encode()
                    iv = initial_vector_string.encode()
                    if act == "display":
                        cipher = AES.new(key, AES.MODE_CFB, iv=iv, segment_size=8)
                        encrypted_bytes = base64.b64decode(str(data).encode())
                        decrypted_bytes = cipher.decrypt(encrypted_bytes)
                        data = decrypted_bytes.decode("utf-8")
                    else:
                        cipher = AES.new(key, AES.MODE_CFB, iv=iv, segment_size=8)
                        encrypted_bytes = cipher.encrypt(str(data).encode())
                        data = base64.b64encode(encrypted_bytes).decode("utf-8")
            except Exception as e:
                print(f"set_enc_dec_user error: {e}")
        return data
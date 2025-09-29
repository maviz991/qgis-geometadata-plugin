# 🔐 Login no geo.cdhu.sp.gov.br

O processo de autenticação no **Geo/CDHU** segue o padrão **form-based login** (login por formulário HTTP).

---

## 1. Endpoint de Login

- **URL:** `https://geo.cdhu.sp.gov.br/login`  
- **Método:** `POST`  
- **Payload esperado:**
  ```http
  username=SEU_USUARIO
  password=SUA_SENHA
  ```

---

## 2. Resposta do Servidor

### ✅ Credenciais válidas
- O servidor cria uma **sessão autenticada**.  
- Retorna um **cookie de sessão** (`SESSION`, `JSESSIONID` ou similar).  
- Pode haver um **redirect** para `/datahub` ou outra rota protegida.  

### ❌ Credenciais inválidas
- Retorna `200 OK` ou `302` para a mesma página de login com mensagem de erro no HTML.  
- Nenhum cookie de sessão válido é enviado.  

---

## 3. Manutenção da Sessão

- Todas as requisições subsequentes devem enviar o **cookie de sessão** no header `Cookie`.  
- É esse cookie que garante o estado autenticado, não o redirecionamento.  

---

## 4. Exemplo em Python (`requests`)

```python
import requests

LOGIN_URL = "https://geo.cdhu.sp.gov.br/login"

with requests.Session() as s:
    # Envia credenciais
    payload = {"username": "usuario", "password": "senha"}
    r = s.post(LOGIN_URL, data=payload, verify=False)

    # Verifica cookies de sessão
    print("Cookies ativos:", s.cookies.get_dict())
    if "SESSION" in s.cookies or "JSESSIONID" in s.cookies:
        print("✅ Login bem-sucedido")
    else:
        print("❌ Falha no login")
```

---

## Resumo

- **POST credenciais** → recebe **cookie de sessão** → usa cookie nas próximas requisições.  
- O **redirecionamento** é apenas um efeito, não o que valida o login.  

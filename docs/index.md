# DFIR con ELK: de los logs al análisis en tiempo real

## Introducción

Este taller forma parte de la décima edición de la Security High School, celebrada los días 22 y 23 de febrero de 2026 en el IES Fidiana y la Universidad de Córdoba.

[Enlace](assets/presentacion.pdf) a la presentación de diapositivas.

## Antes de empezar

- Se recomienda realizar el taller en una máquina virtual [Ubuntu Server](https://ubuntu.com/download/server) con mínimo 8 GB de RAM y 10 GB de almacenamiento libres.
- Es importante contar con acceso a un fichero de logs de autenticación (Linux), por ejemplo `/var/log/auth.log`.

## Instalación de Docker y Docker Compose

A continuación se detallan todos los comandos necesarios para instalar Docker y Docker Compose en Ubuntu Server.

Instalamos dependencias básicas:

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg lsb-release
```

Añadimos la clave GPG oficial de Docker:

```bash
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
```

Añadimos el repositorio de Docker:

```bash
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

Instalamos Docker Engine y Docker Compose:

```bash
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Permitimos el uso de Docker sin sudo:

```bash
sudo usermod -aG docker $USER
newgrp docker
```

Verificamos la instalación y levantamos el contenedor "Hello World!":

```bash
docker --version
docker compose version
docker run --rm hello-world
```

## Creación del proyecto

### Estructura de directorios

```bash
mkdir -p elk-taller/logstash/pipeline
mkdir -p elk-taller/filebeat
```

La estructura final será:

```bash
elk-taller/
├── docker-compose.yml
├── logstash/
│   └── pipeline/
│       └── logstash.conf
└── filebeat/
    └── filebeat.yml
```

## Despliegue del stack ELK

docker-compose.yml

```bash
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.1
    container_name: elasticsearch
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - xpack.ml.enabled=false
      - ES_JAVA_OPTS=-Xms512m -Xmx512m
      - node.store.allow_mmap=false
    ports:
      - "9200:9200"
    volumes:
      - esdata:/usr/share/elasticsearch/data

  logstash:
    image: docker.elastic.co/logstash/logstash:8.11.1
    container_name: logstash
    volumes:
      - ./logstash/pipeline:/usr/share/logstash/pipeline
    depends_on:
      - elasticsearch

  kibana:
    image: docker.elastic.co/kibana/kibana:8.11.1
    container_name: kibana
    ports:
      - "5601:5601"
    environment:
      - XPACK_ENCRYPTEDSAVEDOBJECTS_ENCRYPTIONKEY=0123456789abcdef0123456789abcdef
    depends_on:
      - elasticsearch

  filebeat:
    image: docker.elastic.co/beats/filebeat:8.11.1
    container_name: filebeat
    user: root
    volumes:
      - /var/log/auth.log:/var/log/auth.log:ro
      - ./filebeat/filebeat.yml:/usr/share/filebeat/filebeat.yml:ro
    depends_on:
      - logstash

volumes:
  esdata:
```

## Configuración de Filebeat (ingesta)

Crear filebeat/filebeat.yml

```bash
filebeat.inputs:
  - type: log
    enabled: true
    paths:
      - /var/log/auth.log

output.logstash:
  hosts: ["logstash:5044"]
```

## Configuración de Logstash (procesamiento)

Crear logstash/pipeline/logstash.conf

```bash
input {
  beats {
    port => 5044
  }
}

filter {
  grok {
    match => {
      "message" => [
        "^%{TIMESTAMP_ISO8601:syslog_timestamp} %{HOSTNAME:[host][name]} sshd\[%{NUMBER:pid}\]: Failed password for (invalid user )?%{DATA:[user][name]} from %{IP:[source][ip]} port %{NUMBER:[source][port]} ssh2",
        "^%{TIMESTAMP_ISO8601:syslog_timestamp} %{HOSTNAME:[host][name]} sshd\[%{NUMBER:pid}\]: Accepted password for %{DATA:[user][name]} from %{IP:[source][ip]} port %{NUMBER:[source][port]} ssh2",
        "^%{TIMESTAMP_ISO8601:syslog_timestamp} %{HOSTNAME:[host][name]} sshd\[%{NUMBER:pid}\]: pam_unix\(sshd:session\): session %{WORD:[event][action]} for user %{USERNAME:[user][name]}"
      ]
    }
  }

  date {
    match => [ "syslog_timestamp", "ISO8601" ]
    target => "@timestamp"
  }

  if "Accepted password" in [message] {
    mutate { add_field => { "[event][outcome]" => "success" } }
  }
  if "Failed password" in [message] {
    mutate { add_field => { "[event][outcome]" => "failure" } }
  }
}

output {
  elasticsearch {
    hosts => ["http://elasticsearch:9200"]
    index => "dfir-auth-%{+YYYY.MM.dd}"
  }
}
```

### Corregir permisos de Filebeat

```bash
sudo chown root:root filebeat/filebeat.yml
sudo chmod go-w filebeat/filebeat.yml
```

## Arrancar y comprobar servicios

Levantamos los contenedores:

```bash
docker compose up -d
```

Comprobamos el estado de todos ellos:

```bash
docker ps
```

Comprobamos que Elasticsearch se encuentra funcionando:

```bash
curl -s http://localhost:9200 | head
```

Comprobamos que ya existe el índice que hemos creado para el taller (dfir-auth-*)

```bash
curl -s "http://localhost:9200/_cat/indices/dfir-auth-*?v"
```

Con el siguiente comando comprobamos no solo que existe el índice, sino que hay datos reales dentro:

```bash
curl -s "http://localhost:9200/dfir-auth-*/_count?pretty"
```

## Crear el Data View en Kibana

El siguiente paso será crear un *Data View* en Kibana para que pueda "entender" que índices va a explorar en el *Discover*. Kibana no busca directamente en Elasticsearch a ciegas: necesita un Data View que defina el patrón de índices y el campo de tiempo para filtrar por fechas.

Para ello nos dirigimos en nuestro navegador a `http://IP_DE_LA_VM:5601`.

A continuación, vamos a Stack Management → Data Views → Create data view. Rellenamos con los siguientes datos:

- Name: DFIR Auth
- Index pattern: dfir-auth-*
- Timestamp field: @timestamp

## Ver los eventos en Discover

Abrimos Discover para ver los eventos ya indexados. Nos dirigimos a Analytics → Discover y:

- Seleccionar el Data View DFIR Auth (arriba a la izquierda).
- Ajustar el rango de tiempo (arriba a la derecha) a: Last 15 minutes o Last 1 hour (según cuándo se ingestado).
- Deberían aparecer eventos en la tabla.

## Primeros filtros útiles

En la barra de búsqueda (KQL):

- Solo fallos: `event.outcome : "failure"`
- Solo éxitos: `event.outcome : "success"`
- Por IP: `source.ip : "X.X.X.X"`
- Por usuario: `user.name : "root"`

## Análisis DFIR básico: identificar intentos de fuerza bruta

Identificamos direcciones IP con múltiples fallos de autenticación en un periodo corto de tiempo Este es uno de los casos de uso más clásicos de los logs de autenticación:

- Detección de ataques de fuerza bruta
- Detección de IPs sospechosas
- Primeros indicios de compromiso

### Acción en Kibana

**Análisis por nombre de usuario**

1. Mantener el Data View DFIR Auth
2. En la barra de búsqueda, filtrar solo fallos: `event.outcome : "failure"`
3. En Break down by, seleccionar: `user.name.keyword`

Al agrupar por user.name.keyword podemos ver rápidamente qué cuentas están siendo más atacadas.
Esto es especialmente útil para detectar ataques automatizados contra usuarios comunes o contra cuentas privilegiadas como root.

Manera de interpretar estos resultados:

- Muchos fallos sobre usuarios inexistentes -> enumeración de usuarios
- Muchos fallos sobre un usuario real -> posible objetivo concreto
- Fallos repetidos seguidos de un éxito -> evento crítico a investigar

En un análisis forense o de seguridad, este tipo de vista nos permite pasar de miles de líneas de log a un pequeño conjunto de cuentas que merecen atención inmediata.

**Análisis por dirección IP: orígenes más sospechosos**

1. Mantener el Data View DFIR Auth
2. En la barra de búsqueda, filtrar solo fallos: `event.outcome : "failure"`
3. En Break down by, seleccionar: `source.ip.keyword`

Al agrupar por dirección IP podemos identificar rápidamente orígenes que generan un volumen anómalo de fallos de autenticación, algo típico de ataques automatizados.

Manera de interpretar estos resultados:

- Una IP con muchos fallos -> muy probable ataque de fuerza bruta
- Muchas IPs con pocos intentos -> escaneo distribuido
- IPs internas con fallos -> posible problema de configuración o usuario legítimo

Este tipo de vista nos permite pasar de miles de eventos a unas pocas direcciones IP que merecen ser investigadas o bloqueadas.

### Correlación básica: ¿hubo accesos exitosos tras fallos?

1. Quitamos filtros previos
2. Usamos el filtro: `event.outcome : ("failure" or "success")`
3. En Break by down, seleccionamos: `event.outcome.keyword`

Comparar fallos y éxitos nos permite detectar patrones peligrosos, como accesos válidos desde IPs que antes estaban fallando repetidamente.

### Correlación práctica: ¿una IP con fallos consiguió acceder?

Tomamos una dirección IP que ha generado muchos fallos y comprobamos si esa misma IP aparece asociada a algún acceso exitoso.

1. Mantener el Data View DFIR Auth
2. En la barra de búsqueda, filtrar solo fallos: `event.outcome : "failure"`
3. En Break down by, seleccionar: `source.ip.keyword`

Identificamos una IP con muchos eventos, la más repetida, por ejemplo. A continuación, añadimos un filtro con esa IP al que ya teníamos:

`source.ip : "X.X.X.X" and event.outcome : ("failure" or "success")`

Manera de interpretar estos resultados:

- Solo fallos → ataque bloqueado o sin éxito
- Fallos + éxitos → evento crítico a investigar
- Solo éxitos → acceso legítimo o whitelist

### Guardar esta IP como sospechosa

Guardamos la búsqueda resultante de la correlación anterior como una búsqueda reutilizable en Kibana. De esta forma nuestro análisis no se convierte en algo puntual, podemos construir vistas operativas y reutilizar el trabajo en el tiempo.

Mantenemos nuestra consulta `source.ip : "X.X.X.X" and event.outcome : ("failure" or "success")`, añadimos las columnas deseadas y hacemos clic en **Save** (arriba a la derecha).

Para consultarla podemos entrar en Discover → Open. Puede servir como base para alertas, reglas de detección o análisis recurrentes.

## Reglas de detección: IP con múltiples fallos de autenticación

En este punto vamos a crear una regla automática que detecte cuando una misma IP genera múltiples fallos de autenticación en un periodo corto de tiempo.

Esto automatiza el análisis manual que hemos hecho, deja de depender del analista mirando logs, permite alertar de forma proactiva y es la base de un SOC real.

### Preparar el Log View

Las reglas basadas en logs no utilizan Data Views, sino un Log View. Antes de crear la regla, es necesario indicar a Kibana qué índices contienen los logs que queremos analizar.

1. Accedemos a Observability → Logs → Settings.
2. En Log Sources, seleccionamos Indices
3. En Log indices sustituimos el valor por: `dfir-auth-*`
4. Guardamos los cambios

Con esto indicamos a Kibana que los logs de seguridad del taller se encuentran en los índices dfir-auth-*, y serán utilizados tanto por la aplicación de Logs como por las reglas automáticas.

### Crear una nueva regla

Accedemos a Stack Management → Rules → Create rule, seleccionamos el tipo de regla Log threshold. Este tipo de regla está específicamente diseñado para trabajar con eventos de logs y permite filtrar por campos como event.outcome o source.ip.

Creamos la regla indicando el nombre "Fuerza bruta por SSH", y creando la siguiente consulta:

```bash
Log View Default
when the count
with event.outcome.keyword is failure
is more than 10
for the last 5 minutes
Group By source.ip.keyword
```

**Configurar la acción de alerta**

Para que la alerta sea persistente y analizable, se almacenará como un documento en Elasticsearch.

1.	En Actions, pulsar Add action
2.	Seleccionar Index
3.  Creamos el conector con nombre DFIR Auth e índice `dfir-alerts-auth`

En el campo Document to index, creamos el siguiente JSON:

```json
{
  "@timestamp": "{{date}}",
  "rule.name": "Fuerza bruta por SSH",
  "alert.message": "Posible ataque de fuerza bruta por SSH desde {{context.group}}",
  "source.ip": "{{context.group}}",
  "event.category": "authentication",
  "event.type": "alert",
  "event.outcome": "failure"
}
```

Guardamos la regla y desde este momento podemos ver los resultados, por ejemplo, con el siguiente comando:

`curl -s http://localhost:9200/dfir-alerts-auth/_search?pretty`

#### Crear un Data View para las alertas

Para poder visualizar las alertas en Discover, crear un nuevo Data View.

1. Accedemos a Stack Management → Data Views → Create data view
2. Configuramos:
    - Name: DFIR Alerts Auth
    - Index pattern: dfir-alerts-auth
3. Guardar

En este punto podemos a ir a Discover y seleccionar el Data View "DFIR Alerts Auth" para ver las alertas que se han creado.

## Conclusión

En este taller hemos construido un flujo completo y realista de detección de incidentes de seguridad sobre la pila ELK, partiendo de logs en bruto y llegando hasta la generación de alertas automáticas persistentes.

A lo largo del proceso hemos trabajado con la arquitectura real del stack, configurado la ingesta de eventos de autenticación, normalizado los datos, realizado análisis manual y, finalmente, automatizado ese análisis mediante una regla de detección basada en comportamiento. El resultado no depende de la observación constante del analista, sino que convierte los eventos en conocimiento accionable.

Aunque el entorno utilizado se apoya en una licencia básica y presenta limitaciones en cuanto a notificaciones externas, el núcleo del sistema es plenamente funcional: detección, correlación, persistencia de evidencias y análisis posterior. En un entorno productivo, este mismo flujo podría ampliarse fácilmente con notificaciones por correo, mensajería corporativa o integraciones SOAR.

Este laboratorio refleja, a pequeña escala, el funcionamiento real de un SOC moderno: datos bien estructurados, detecciones claras, automatización y capacidad de respuesta. A partir de aquí, las posibilidades de ampliación son numerosas, pero la base ya está construida.

El objetivo no era solo aprender a usar ELK, sino entender cómo convertir logs en alertas y alertas en decisiones.
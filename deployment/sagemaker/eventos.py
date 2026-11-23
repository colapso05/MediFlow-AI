import json
import os
from uuid import uuid4

import pika


COLA = "mediflow.predicciones"


def conectar(url: str):
    parametros = pika.URLParameters(url)
    parametros.socket_timeout = 3
    parametros.stack_timeout = 5
    parametros.blocked_connection_timeout = 3
    return pika.BlockingConnection(parametros)


def publicar(url: str, resultado: dict) -> None:
    evento = {
        "id": str(uuid4()),
        "tipo": "prediccion.generada",
        "version_modelo": resultado["version_modelo"],
        "probabilidad": resultado["probabilidad"],
        "priorizar_recordatorio": resultado["priorizar_recordatorio"],
    }
    with conectar(url) as conexion:
        canal = conexion.channel()
        canal.queue_declare(queue=COLA, durable=True)
        canal.confirm_delivery()
        canal.basic_publish(
            exchange="", routing_key=COLA, body=json.dumps(evento).encode(), mandatory=True,
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
        )


def consumir(canal, metodo, propiedades, cuerpo):
    print(cuerpo.decode("utf-8"), flush=True)
    canal.basic_ack(delivery_tag=metodo.delivery_tag)


def main() -> None:
    with conectar(os.environ["AMQP_URL"]) as conexion:
        canal = conexion.channel()
        canal.queue_declare(queue=COLA, durable=True)
        canal.basic_qos(prefetch_count=10)
        canal.basic_consume(queue=COLA, on_message_callback=consumir)
        canal.start_consuming()


if __name__ == "__main__":
    main()

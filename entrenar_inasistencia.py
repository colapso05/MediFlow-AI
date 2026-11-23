"""Entrena el modelo de demostración sobre citas ficticias reproducibles."""

import json
import random
from math import exp

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

from backend.prediccion import MODELO, VARIABLES, variables_modelo


def main() -> None:
    aleatorio = random.Random(1102)
    variables = []
    resultados = []
    for _ in range(4_000):
        dias = min(60, aleatorio.expovariate(1 / 18))
        dia = aleatorio.randrange(7)
        hora = aleatorio.randrange(8, 20)
        fila = variables_modelo(dias, dia, hora)
        log_odds = -2.7 + 1.4 * fila[0] + 0.6 * fila[1] + 0.45 * fila[2]
        riesgo_simulado = 1 / (1 + exp(-log_odds))
        variables.append(fila)
        resultados.append(int(aleatorio.random() < riesgo_simulado))

    x_train, x_test, y_train, y_test = train_test_split(
        variables, resultados, test_size=0.25, stratify=resultados, random_state=1102,
    )
    clasificador = LogisticRegression().fit(x_train, y_train)
    puntuaciones = clasificador.predict_proba(x_test)[:, 1]
    umbral = 0.25
    predicciones = puntuaciones >= umbral
    modelo = {
        "version": "inasistencia-demo-1",
        "datos_entrenamiento": "sinteticos",
        "variables": VARIABLES,
        "coeficientes": clasificador.coef_[0].tolist(),
        "intercepto": float(clasificador.intercept_[0]),
        "umbral": umbral,
        "filas_entrenamiento": len(y_train),
        "filas_prueba": len(y_test),
        "metricas_prueba": {
            "accuracy": accuracy_score(y_test, predicciones),
            "precision": precision_score(y_test, predicciones),
            "recall": recall_score(y_test, predicciones),
            "f1": f1_score(y_test, predicciones),
            "roc_auc": roc_auc_score(y_test, puntuaciones),
        },
    }
    MODELO.write_text(json.dumps(modelo, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(modelo["metricas_prueba"], indent=2))


if __name__ == "__main__":
    main()

"""Genera las graficas de la Wiki a partir de perf/results/<variante>/.

    python perf/graficas.py   # escribe perf/results/graficas/*.png (requiere matplotlib)
"""
import csv, json, os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, 'perf', 'results')
OUT = os.path.join(RES, 'graficas')
os.makedirs(OUT, exist_ok=True)
ESC = ['baseline', 'load', 'stress']
COL = {'sin-pool': '#2a78d6', 'con-pool': '#eb6834'}
NOM = {'sin-pool': 'Sin pool', 'con-pool': 'Con pool (HikariCP)'}
TXT, TXT2, GRID, BG = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'

plt.rcParams.update({'font.size': 10, 'text.color': TXT, 'axes.labelcolor': TXT2, 'xtick.color': TXT2,
                     'ytick.color': TXT2, 'axes.edgecolor': GRID, 'figure.facecolor': BG, 'axes.facecolor': BG})


def fila(v, e):
    return json.load(open(os.path.join(RES, v, f'server-{e}.json')))


def barras(ax, clave, titulo):
    w = 0.36
    for i, v in enumerate(COL):
        xs = [k + (i - 0.5) * (w + 0.02) for k in range(len(ESC))]
        ys = [fila(v, e)[clave] for e in ESC]
        ax.bar(xs, ys, w, color=COL[v], label=NOM[v], edgecolor=BG, linewidth=2)
        for x, y in zip(xs, ys):
            ax.text(x, y, f'{y:.2f}', ha='center', va='bottom', fontsize=8, color=TXT2)
    ax.set_xticks(range(len(ESC)), ['Baseline\n20 VUs', 'Carga\n200 VUs', 'Estrés\n600 VUs'])
    ax.set_title(titulo, loc='left', fontsize=11, color=TXT)
    ax.set_ylabel('ms')
    ax.grid(axis='y', color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)


fig, axs = plt.subplots(1, 2, figsize=(10, 4))
barras(axs[0], 'k6_p95_ms', 'p95 medido por k6 (cliente)')
barras(axs[1], 'srv_p95_ms', 'p95 medido por Actuator (servidor)')
axs[0].legend(frameon=False, loc='upper left')
fig.tight_layout()
fig.savefig(os.path.join(OUT, 'p95-cliente-vs-servidor.png'), dpi=130)

fig, ax = plt.subplots(figsize=(10, 3.6))
for v in COL:
    t, h = [], []
    for r in csv.DictReader(open(os.path.join(RES, v, 'timeline-stress.csv'))):
        if r['hilos_vivos']:
            t.append(int(r['t_s']) / 60)
            h.append(float(r['hilos_vivos']))
    ax.plot(t, h, color=COL[v], linewidth=2, label=NOM[v])
ax.axvspan(5, 8, color=GRID, alpha=0.5, linewidth=0)
ax.text(6.5, ax.get_ylim()[0] + 4, '600 VUs sostenidos', ha='center', va='bottom', fontsize=8, color=TXT2)
ax.set_title('Hilos vivos de la JVM durante el escenario de estrés', loc='left', fontsize=11)
ax.set_xlabel('minutos')
ax.set_ylabel('hilos')
ax.grid(axis='y', color=GRID, linewidth=0.8)
for s in ('top', 'right'):
    ax.spines[s].set_visible(False)
ax.legend(frameon=False, loc='lower right')
fig.tight_layout()
fig.savefig(os.path.join(OUT, 'hilos-estres.png'), dpi=130)
print('ok')

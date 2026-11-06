# setimoandar.com

Site oficial do **7° andar**, podcast de cinema apresentado por Rai Rezende.

O conteúdo vem do Substack ([7andar.substack.com](https://7andar.substack.com)): a cada push e a cada 3 horas o GitHub Actions busca os posts, gera o site estático e publica no GitHub Pages. Episódio novo no Substack aparece aqui sozinho.

## Como funciona

| Arquivo | Papel |
|---|---|
| `scripts/sync.py` | Baixa todos os posts do Substack para `data/posts.json` |
| `data/episodes-extra.json` | Dados curados por episódio: filme, ano, direção, ID do YouTube |
| `scripts/build.py` | Gera `dist/` (páginas, artes em WebP, imagens de compartilhamento) |
| `src/` | CSS, JS e as marcas em SVG (vetorizadas da arte original) |

Para um episódio novo, só falta adicionar o filme em `data/episodes-extra.json` (o ID do YouTube é preenchido automaticamente quando disponível). Sem essa entrada o episódio aparece normalmente, só sem a ficha do filme.

## Rodar localmente

```bash
pip install -r requirements.txt
python scripts/sync.py
python scripts/build.py
python -m http.server -d dist 8000
```

## Domínio

`setimoandar.com` no Cloudflare apontando para o GitHub Pages (registros A/AAAA no apex e CNAME `www` para `svallory.github.io`).

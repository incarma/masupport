Remove-Item Env:APP_ENV -ErrorAction SilentlyContinue
Remove-Item Env:ENV -ErrorAction SilentlyContinue
Remove-Item Env:ENV_FILE -ErrorAction SilentlyContinue

$env:APP_ENV="dev"
python -m celery -A web_ma worker --loglevel=info --pool=solo -c 1

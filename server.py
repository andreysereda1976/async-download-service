from os import path, getpgid
from aiohttp import web
import aiofiles
import asyncio
import datetime
import logging


INTERVAL_SECS = 1
DIR = '/home/andrey/5_My_projects/Dvmn/photozip/'
TEST_DIR = f'{DIR}Dvmn/'
SERVER_DIR = f'{DIR}async-download-service/test_photos/'

logging.basicConfig(
    format=u'%(filename)s[LINE:%(lineno)d]# %(levelname)-8s [%(asctime)s]  %(message)s',
    level=logging.DEBUG)


async def uptime_handler(request):
    response = web.StreamResponse()

    # Большинство браузеров не отрисовывают частично загруженный контент,
    # только если это не HTML.
    # Поэтому отправляем клиенту именно HTML, указываем это в Content-Type.
    response.headers['Content-Type'] = 'text/html'

    # Отправляет клиенту HTTP заголовки
    await response.prepare(request)

    while True:
        formatted_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f'{formatted_date}<br>'  # <br> — HTML тег переноса строки

        # Отправляет клиенту очередную порцию ответа
        await response.write(message.encode('utf-8'))

        await asyncio.sleep(INTERVAL_SECS)


async def archivate(request):
    archive_hash = request.match_info.get('archive_hash', "7kna")
    logging.debug(f'ARCH_HASH: {archive_hash}')
    path_exists = path.exists(f'{SERVER_DIR}{archive_hash}')
    logging.debug(f'Path exists: {path_exists}')
    if not path_exists:
        logging.error("Path doesn't exist")
        raise web.HTTPNotFound(
            text="Sorry. Archive you are asking for doesn't exist or was deleted")
    response = web.StreamResponse()
    response.headers['Content-Type'] = 'application/octet-stream'
    response.headers['Content-Disposition'] = f'attachment; filename="{archive_hash}.zip"'

    # Отправляет клиенту HTTP заголовки
    await response.prepare(request)

    process = await asyncio.create_subprocess_shell(
        f'exec zip -rj - {SERVER_DIR}{archive_hash}',
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    file = open(f'{TEST_DIR}{archive_hash}.zip', 'w+b')
    file.seek(0)
    iteration = 0

    try:
        while True:
            iteration += 1
            stdout = await process.stdout.read(250000)
            if process.stdout.at_eof():
                break
            logging.debug(
                f'Sending archive chunk ... iteration:\
                {iteration}, bites: {len(stdout)}')
            file.write(stdout)
            # Отправляет клиенту очередную порцию ответа
            await response.write(stdout)
            # Пауза для проверки разрыва соединения по инициативе клиента
            await asyncio.sleep(1)

    except (asyncio.CancelledError, SystemExit):
        logging.debug('Download was interrupted')
        print(process.pid, getpgid(process.pid))
        # отпускаем перехваченный CancelledError
        raise

    finally:
        # закрывать файл и соединение,
        # останавливать дочерний процесс даже в случае ошибки
        await response.write_eof()
        file.close()
        process.terminate()
        _ = await process.communicate()

    return response


async def handle_index_page(request):
    async with aiofiles.open('index.html', mode='r') as index_file:
        index_contents = await index_file.read()
    return web.Response(text=index_contents, content_type='text/html')


if __name__ == '__main__':
    app = web.Application()
    app.add_routes([
        web.get('/', handle_index_page),
        web.get('/archive/{archive_hash}/', archivate),
        web.get('/uptime/', uptime_handler),
    ])
    # try:
    web.run_app(app)

"""Windows Jarvis: python main.py [--selftest | --text]"""
import argparse
import asyncio
import sys
import threading
import webbrowser
from app.runtime import Runtime
from app.main import create_app

async def run(args):
    import uvicorn
    runtime=Runtime()
    server=uvicorn.Server(uvicorn.Config(create_app(runtime),host='127.0.0.1',port=args.port,proxy_headers=False,log_level='warning',timeout_graceful_shutdown=5))
    # Let the root handle Ctrl+C; Uvicorn owns cleanup through its lifespan.
    server_task=asyncio.create_task(server.serve())
    while not server.started and not server_task.done():await asyncio.sleep(0.05)
    if server_task.done():await server_task;return
    print(f'Jarvis HUD: http://127.0.0.1:{args.port}\nType your message, yes/no for confirmations, /stop to interrupt, /quit to exit.',flush=True)
    if not args.no_browser:webbrowser.open(f'http://127.0.0.1:{args.port}')
    if not args.text:
        try:await runtime.start_voice()
        except Exception as exc:
            runtime.microphone_error=runtime.safe_error(exc)
            print('Microphone unavailable: '+runtime.microphone_error+'\nTyped text and HUD remain usable.',flush=True)
        try:runtime.hotkeys.start()
        except Exception as exc:print(runtime.safe_error(exc),flush=True)
    queue=asyncio.Queue()
    loop=asyncio.get_running_loop()
    def read_stdin():
        for line in sys.stdin:
            try:loop.call_soon_threadsafe(queue.put_nowait,line.strip())
            except RuntimeError:return
        try:loop.call_soon_threadsafe(queue.put_nowait,None)
        except RuntimeError:pass
    threading.Thread(target=read_stdin,daemon=True).start()
    active=set()
    async def turn(text):
        try:await runtime.native_turn(text,'console')
        except Exception as exc:await runtime.emit('error',runtime.safe_error(exc))
    try:
        while not server_task.done():
            try:text=await asyncio.wait_for(queue.get(),0.5)
            except asyncio.TimeoutError:continue
            if text is None:
                await server_task;break
            if not text:continue
            if text=='/quit':break
            if text=='/stop':runtime.speaker.interrupt();continue
            pending=next(((token,item) for token,item in runtime.confirmations.items() if item[1]=='console'),None)
            if pending and text.lower() in {'yes','oui','no','non'}:
                runtime.answer_confirmation(pending[0],text.lower() in {'yes','oui'});continue
            task=asyncio.create_task(turn(text));active.add(task);task.add_done_callback(active.discard)
    finally:
        for task in active:task.cancel()
        if active:await asyncio.gather(*active,return_exceptions=True)
        runtime.stop.set();runtime.wake.set();runtime.speaker.interrupt()
        await runtime.emit('shutdown',True)
        server.should_exit=True
        await server_task

def main():
    if hasattr(sys.stdout, 'reconfigure'):sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    parser=argparse.ArgumentParser(description='Jarvis native Windows voice assistant')
    parser.add_argument('--selftest',action='store_true',help='Run real integration diagnostics, with explicit consent for changing actions')
    parser.add_argument('--text',action='store_true',help='Start HUD and typed mode without background microphone/wake')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    try:
        if args.selftest:
            from app.selftest import selftest
            code=asyncio.run(selftest())
            raise SystemExit(code)
        asyncio.run(run(args))
    except KeyboardInterrupt:print('\nJarvis stopped.')
if __name__=='__main__':main()

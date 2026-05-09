import asyncio
import websockets

async def handle(websocket, path=None):
    # دریافت و اعتبارسنجی مقصد
    try:
        target = await websocket.recv()
        host, port = target.split(":")
        port = int(port)
    except Exception:
        await websocket.close(1008, "Invalid target format")
        return

    try:
        reader, writer = await asyncio.open_connection(host, port)
    except Exception as e:
        await websocket.close(1011, f"TCP connect failed: {e}")
        return

    async def ws_to_tcp():
        try:
            while True:
                data = await websocket.recv()
                writer.write(data)
                await writer.drain()
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            writer.close()

    async def tcp_to_ws():
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                await websocket.send(data)
        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    await asyncio.gather(ws_to_tcp(), tcp_to_ws())

async def main():
    async with websockets.serve(handle, "0.0.0.0", 8765):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())

import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="AI Changemakers 100x100 сервер")
    parser.add_argument("--host", default="127.0.0.1", help="Хост хаяг (0.0.0.0 бол сүлжээнд нээнэ)")
    parser.add_argument("--port", type=int, default=8000, help="Портын дугаар")
    parser.add_argument("--reload", action="store_true", help="Хөгжүүлэлтийн горимд автомат дахин ачаалах")
    args = parser.parse_args()

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()

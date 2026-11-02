import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        del sys.argv[1]
        from commentextract.cli import main
        raise SystemExit(main())
    from commentextract.app import main
    raise SystemExit(main())

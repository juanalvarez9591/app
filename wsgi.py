from app import app, init_app

# Initialize the database
init_app(app)

if __name__ == "__main__":
    app.run()
# First stage: Build and install commlib-cli
FROM nikolaik/python-nodejs:python3.8-nodejs18-slim

# Install git
RUN apt-get update && apt-get install -y git

# Install commlib-py
RUN pip install git+https://github.com/robotics-4-all/commlib-py.git@master

# Clone commlib-cli repository
RUN git clone https://github.com/robotics-4-all/commlib-cli.git /commlib-cli

# Set working directory to commlib-cli
WORKDIR /commlib-cli

# Install commlib-cli
RUN pip install -r requirements.txt
RUN python setup.py develop --user

# Create and change to the app directory.
WORKDIR /telegram-bot

COPY package*.json ./

# Install production dependencies.
RUN npm install --production

COPY . .

# Set PATH to include local bin
ENV PATH=/root/.local/bin:$PATH

CMD [ "node", "index.mjs" ]

EXPOSE 3131

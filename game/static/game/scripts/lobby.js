const UI = {
    "WAITING": {
        el: document.getElementById("lobby_ui"),
        enter: function() {
            this.el.classList.add("d-block");
            this.el.classList.remove("d-none");
        },
        exit: function() {
            this.el.classList.add("d-none");
            this.el.classList.remove("d-block");
        }
    },
    "ASSIGNING_ROLES": {
        el: document.getElementById("assigning_roles_ui"),
        enter: function() {
            this.el.classList.add("d-block");
            this.el.classList.remove("d-none");
        },
        exit: function() {
            this.el.classList.add("d-none");
            this.el.classList.remove("d-block");
        }
    },
    "ROLE": {
        el: document.getElementById("roles_ui"),
        enter: function() {
            this.el.classList.add("d-block");
            this.el.classList.remove("d-none");
        },
        exit: function() {
            this.el.classList.add("d-none");
            this.el.classList.remove("d-block");
        }
    },
};

let currentState = null;

const roomCode = document.getElementById("room-code").textContent.trim();
const player = document.getElementById("player-name").textContent.trim();
console.log("Connecting to lobby with room code:", roomCode, "and player:", player);
const ws = new WebSocket(`ws://192.168.1.167:8000/ws/lobby/${roomCode}/${player}/`);

const playersRow = document.getElementById("players-row");
const players = new Map(); // evitar duplicados

const modal = new bootstrap.Modal(document.getElementById('leaveRoomModal'));

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log("Mensaje recibido:", data);

    if (data.type === "build_grid") {
        // Añadir todos los jugadores existentes
        data.players.forEach(p => addPlayerCard(p));
        setPlayerCount(players.size);
    }

    if (data.type === "player_joined") {
        if (players.has(data.player.name)) {
            console.log("Jugador ya existe:", data.player);
            return; // Evitar duplicados
        }
        console.log("Player joined:", data.player);
        addPlayerCard(data.player);
        setPlayerCount(players.size);
    }

    if (data.type === "player_left") {
        removePlayerCard(data.player);
        setPlayerCount(players.size);
    }

    if (data.type === "player_ready") {
        setPlayerReadyState(data.player);
    }

    if (data.type === "state_change") {
        console.log("Game state changed to:", data.state);
        setUIState(data.state);
    }

    if (data.type === "role_assigned") {
        setRole(data.role);
    }
};

function addPlayerCard(player) {

    // Crear columna Bootstrap
    const col = document.createElement("div");
    col.className = "col-6";  
    col.id = `${player.name}`;

    // Crear tarjeta Bootstrap
    col.innerHTML = `
        <div class="card border-danger" id="${player.name}_card">
            <!--img src="..." class="card-img-top" alt="..."-->
            <img src="" class="card-img-top"></img>
            <div class="card-body">
                <h5 class="card-title text-center">${player.name}</h5>
            </div>
        </div>
    `;

    const player_card = col.querySelector(".card");
    if (player.ready) {
        player_card.classList.remove("border-danger");
        player_card.classList.add("border-success");
    }

    players.set(player.name, col);
    playersRow.appendChild(col);
}

function setPlayerCount(count) {
    const playersHeader = document.getElementById("players");
    playersHeader.textContent = `Players: ${count}`;
}

function removePlayerCard(player) {
    const col = document.getElementById(`${player.name}`);
    if (col) col.remove();
    players.delete(player.name);
}

function setPlayerReadyState(player_ready) {
    const card = document.getElementById(`${player_ready.name}_card`);
    card.classList.remove(player_ready.ready ? "border-danger" : "border-success");
    card.classList.add(player_ready.ready ? "border-success" : "border-danger");

    const btn = document.getElementById("ready-btn");
    if (player_ready.name === player) {
        isReady = player_ready.ready;
        if (isReady) {
            btn.textContent = "Ready";
            btn.classList.remove("btn-danger");
            btn.classList.add("btn-success");
        } else {
            btn.textContent = "Not ready";
            btn.classList.remove("btn-success");
            btn.classList.add("btn-danger");
        }
    }
}

function setUIState(newState) {
    if (currentState === newState) return;
    console.log(`Cambiando UI de ${currentState} a ${newState}`);


    // Apaga la UI anterior
    if (currentState) UI[currentState].exit();

    // Enciende la nueva
    UI[newState].enter();

    currentState = newState;
}

function setRole(role) {
    const roleTitle = document.getElementById("role-name");
    const img = document.getElementById("role-img");
    const roleDesc = document.getElementById("role-desc");

    roleTitle.innerText = role["name"];
    img.setAttribute("src", role["image"]);
}

document.addEventListener("DOMContentLoaded", () => {

    history.pushState({ room: true }, "", "");
    history.pushState({ room: true }, "", "");
    console.log(history.state)

    window.addEventListener("popstate", (event) => {
        console.log("Evento popstate:", event.state);
        if (event.state && event.state.room) {

            // Recolocar estado para mantener la captura
            history.pushState({ room: true }, "", "");

            // Acción al pulsar atrás
            showLeaveRoomModal();
        }
    });

    document.getElementById("ready-form").addEventListener("submit", function (event) {
        event.preventDefault();  // <-- Bloquea el envío tradicional

        // Enviar estado al servidor si es necesario
        ws.send(JSON.stringify({ type: "player_ready", player: player }));
    });
});

function showLeaveRoomModal() {
    // Tu modal JS/HTML
    modal.show();
}

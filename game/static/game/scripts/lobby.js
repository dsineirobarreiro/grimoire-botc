
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
};

function addPlayerCard(player) {

    // Crear columna Bootstrap
    const col = document.createElement("div");
    col.className = "col-6";  
    col.id = `${player.name}`;

    // Crear tarjeta Bootstrap
    col.innerHTML = `
        <div class="card">
            <!--img src="..." class="card-img-top" alt="..."-->
            <img src="" class="card-img-top"></img>
            <div class="card-body">
                <h5 class="card-title text-center">${player.name}</h5>
            </div>
        </div>
    `;

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
});

function showLeaveRoomModal() {
    // Tu modal JS/HTML
    modal.show();
}

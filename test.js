// const joe = new WebSocket(
//   "ws://127.0.0.1:8000/ws?token=",
// );
// joe.onopen=()=>console.log("connected") joe.onclose=()=>console.log("closed") joe.onerror=(e)=>console.log(e) (e)=>console.log(e)


const joe = new WebSocket("ws://127.0.0.1:8000/ws?token=");

joe.onopen = () => console.log("connected");
joe.onclose = () => console.log("closed");
joe.onerror = (e) => console.log("error", e);
joe.onmessage = (e) => console.log("message received", e.data);

const dex = new WebSocket("ws://127.0.0.1:8000/ws?token=");

dex.onopen = () => console.log("connected");
dex.onclose = () => console.log("closed");
dex.onerror = (e) => console.log("error", e);
dex.onmessage = (e) => console.log("message received", e.data);




joe.send(JSON.stringify({
    receiver_id:1,
    message:"hello"
}))
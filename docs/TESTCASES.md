# Test Cases – Rock Paper Scissors

## TC01 – Server start
- Start server
- Expected: Server listens on port and prints status

## TC02 – Client connect
- Client connects to server
- Expected: Server accepts connection, client receives welcome message

## TC03 – Create room
- Client A creates room
- Expected: Room created successfully

## TC04 – Join room
- Client B joins room
- Expected: Both clients see each other in room

## TC05 – Play round
- Both clients send move
- Expected: Server calculates result correctly

## TC06 – Client disconnect
- One client disconnects
- Expected: Server handles disconnect gracefully

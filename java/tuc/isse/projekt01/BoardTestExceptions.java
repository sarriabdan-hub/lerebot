/**
 * @author Haris Masood <haris.masood@tu-clausthal.de>
 *
 */
package tuc.isse.projekt01;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import tuc.isse.projekt01.model.Ball;
import tuc.isse.projekt01.model.Board;
import tuc.isse.projekt01.model.Color;
import tuc.isse.projekt01.model.Direction;
import tuc.isse.projekt01.model.NotInRangeException;
import tuc.isse.projekt01.model.NotYourBallException;
import tuc.isse.projekt01.model.OutOfGameException;
import tuc.isse.projekt01.model.Role;

import org.junit.jupiter.api.BeforeEach;

public class BoardTestExceptions {

    private Board board;

    @BeforeEach
    public void setUp() {
        board = new Board();
        board.clearBoard(); // Start empty to test specific scenarios
    }

    // =================================================================
    // 1. Initial Setup Test
    // =================================================================
    @Test
    public void testInitialBoardSetup() {
        // We create a FRESH board here to check the automatic setup
        Board freshBoard = new Board();
        String boardString = freshBoard.toString();

        // Check Visual Representation
        assertTrue(boardString.contains("[O]"), "Board must contain White King");
        assertTrue(boardString.contains("[X]"), "Board must contain Black King");

        // Check Internal Data (White Team)
        Ball whiteKing = freshBoard.getBall(0, 0);
        assertEquals(Role.KING, whiteKing.getRole());
        assertEquals(Color.WHITE, whiteKing.getColor());

        // Check Internal Data (Black Team)
        Ball blackKing = freshBoard.getBall(6, 6);
        assertEquals(Role.KING, blackKing.getRole());
        assertEquals(Color.BLACK, blackKing.getColor());
    }

    // =================================================================
    // 2. NotInRangeException (Boundary Testing)
    // Covers: White/Black, All 4 sides (Top, Bottom, Left, Right)
    // =================================================================
    @Test
    public void testNotInRangeException() {
        // 1. Column too low (Left of board) - White Player
        assertThrows(NotInRangeException.class, () -> {
            board.moveBall(Color.WHITE, -1, 3, Direction.UP);
        });

        // 2. Column too high (Right of board) - Black Player
        assertThrows(NotInRangeException.class, () -> {
            board.moveBall(Color.BLACK, 7, 3, Direction.DOWN);
        });

        // 3. Row too low (Above board) - White Player
        assertThrows(NotInRangeException.class, () -> {
            board.moveBall(Color.WHITE, 3, -1, Direction.LEFT);
        });

        // 4. Row too high (Below board) - Black Player
        assertThrows(NotInRangeException.class, () -> {
            board.moveBall(Color.BLACK, 3, 7, Direction.RIGHT);
        });
    }

    // =================================================================
    // 3. NotYourBallException (Ownership Testing)
    // Covers: Moving Empty cells, White moving Black, Black moving White
    // =================================================================
    @Test
    public void testNotYourBallException() {
        // 1. Selecting an EMPTY cell (Air)
        // (3,3) is empty due to clearBoard()
        assertThrows(NotYourBallException.class, () -> {
            board.moveBall(Color.WHITE, 3, 3, Direction.UP);
        });

        // 2. White Player tries to move Black Ball
        board.setBallAt(2, 2, new Ball(Color.BLACK, Role.RESIDENT));
        assertThrows(NotYourBallException.class, () -> {
            board.moveBall(Color.WHITE, 2, 2, Direction.DOWN);
        });

        // 3. Black Player tries to move White Ball
        board.setBallAt(5, 5, new Ball(Color.WHITE, Role.RESIDENT));
        assertThrows(NotYourBallException.class, () -> {
            board.moveBall(Color.BLACK, 5, 5, Direction.LEFT);
        });
    }

    // =================================================================
    // 4. OutOfGameException (Illegal Move / Suicide Testing)
    // Covers: White/Black, Direct Suicide, Pushing Friend off
    // =================================================================
    @Test
    public void testOutOfGameException() {
        // --- SCENARIO A: Direct Suicide (Self moves off) ---

        // 1. White moves UP off the board (at 0,0)
        board.setBallAt(0, 0, new Ball(Color.WHITE, Role.RESIDENT));
        assertThrows(OutOfGameException.class, () -> {
            board.moveBall(Color.WHITE, 0, 0, Direction.UP);
        });

        // 2. Black moves DOWN off the board (at 6,6)
        board.setBallAt(6, 6, new Ball(Color.BLACK, Role.RESIDENT));
        assertThrows(OutOfGameException.class, () -> {
            board.moveBall(Color.BLACK, 6, 6, Direction.DOWN);
        });

        // 3. White moves LEFT off the board (at 0,3)
        board.setBallAt(0, 3, new Ball(Color.WHITE, Role.RESIDENT));
        assertThrows(OutOfGameException.class, () -> {
            board.moveBall(Color.WHITE, 0, 3, Direction.LEFT);
        });

        // 4. Black moves RIGHT off the board (at 6,3)
        board.setBallAt(6, 3, new Ball(Color.BLACK, Role.RESIDENT));
        assertThrows(OutOfGameException.class, () -> {
            board.moveBall(Color.BLACK, 6, 3, Direction.RIGHT);
        });

        // --- SCENARIO B: Friendly Fire (Pushing Teammate off) ---

        // 5. White pushes White off (UP)
        // Setup: [White Driver] -> [White Passenger] -> Edge
        board.setBallAt(1, 1, new Ball(Color.WHITE, Role.RESIDENT)); // Driver
        board.setBallAt(1, 0, new Ball(Color.WHITE, Role.RESIDENT)); // Passenger (Edge)
        // Note: Force (Column Count) needs to be 2 for this to trigger properly
        // We assume setUp() clears board, so we have exactly these 2 balls.

        assertThrows(OutOfGameException.class, () -> {
            board.moveBall(Color.WHITE, 1, 1, Direction.UP);
        });

        // 6. Black pushes Black off (DOWN)
        // Setup: [Black Driver] -> [Black Passenger] -> Edge
        board.setBallAt(5, 5, new Ball(Color.BLACK, Role.RESIDENT)); // Driver
        board.setBallAt(5, 6, new Ball(Color.BLACK, Role.RESIDENT)); // Passenger (Edge)

        assertThrows(OutOfGameException.class, () -> {
            board.moveBall(Color.BLACK, 5, 5, Direction.DOWN);
        });
    }
}
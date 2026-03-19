package tuc.isse.projekt01;

import org.junit.Test;

import tuc.isse.projekt01.model.Ball;
import tuc.isse.projekt01.model.Board;
import tuc.isse.projekt01.model.Color;
import tuc.isse.projekt01.model.Direction;
import tuc.isse.projekt01.model.Role;
import tuc.isse.projekt01.model.Winner;

import static org.junit.Assert.*;

/**
 * JUnit Test cases for Task d (Aufgabenblatt 07).
 * Covers movement in all 4 directions and all win conditions.
 * @author Haris Masood <haris.masood@tu-clausthal.de>
 */
public class BoardTest_P2 {

    // 1. Check if the upward movement was successful. [cite: 205]
    @Test
    public void testMoveUp() throws Exception {
        Board board = new Board();
        board.clearBoard();

        // Setup: White Resident at (3,3).
        // We add a neighbor at (4,3) so the Horizontal Row Count is 2.
        board.setBallAt(3, 3, new Ball(Color.WHITE, Role.RESIDENT));
        board.setBallAt(4, 3, new Ball(Color.WHITE, Role.RESIDENT));

        // Execute: Move UP. Distance = 2. Target: (3,1).
        board.moveBall(Color.WHITE, 3, 3, Direction.UP);

        // Verify: Ball should be at (3,1)
        assertNotNull("Ball should be at 3,1", board.getBall(3, 1));
    }

    // 2. Check if the downward movement was successful. [cite: 206]
    @Test
    public void testMoveDown() throws Exception {
        Board board = new Board();
        board.clearBoard();

        // Setup: White Resident at (0,0).
        // We add a neighbor at (1,0) so the Horizontal Row Count is 2.
        board.setBallAt(0, 0, new Ball(Color.WHITE, Role.RESIDENT));
        board.setBallAt(1, 0, new Ball(Color.WHITE, Role.RESIDENT));

        // Execute: Move DOWN. Distance = 2. Target: (0,2).
        board.moveBall(Color.WHITE, 0, 0, Direction.DOWN);

        // Verify: Ball should be at (0,2)
        assertNotNull("Ball should be at 0,2", board.getBall(0, 2));
    }

    // 3. Check if the leftward movement was successful. [cite: 208]
    @Test
    public void testMoveLeft() throws Exception {
        Board board = new Board();
        board.clearBoard();

        // Setup: Black Resident at (3,3).
        // We add a neighbor at (3,4) so the Vertical Column Count is 2.
        board.setBallAt(3, 3, new Ball(Color.BLACK, Role.RESIDENT));
        board.setBallAt(3, 4, new Ball(Color.BLACK, Role.RESIDENT));

        // Execute: Move LEFT. Distance = 2. Target: (1,3).
        board.moveBall(Color.BLACK, 3, 3, Direction.LEFT);

        // Verify: Ball should be at (1,3)
        assertNotNull("Ball should be at 1,3", board.getBall(1, 3));
    }

    // 4. Check if the rightward movement was successful.
    // (PDF typo says 'unten' twice, assuming 'rechts' is intended).
    @Test
    public void testMoveRight() throws Exception {
        Board board = new Board();
        board.clearBoard();

        // Setup: White Resident at (0,0).
        // Vertical Column Count is 1 (itself). Distance = 1.
        board.setBallAt(0, 0, new Ball(Color.WHITE, Role.RESIDENT));

        // Execute: Move RIGHT. Distance = 1. Target: (1,0).
        board.moveBall(Color.WHITE, 0, 0, Direction.RIGHT);

        // Verify: Ball should be at (1,0)
        assertNotNull("Ball should be at 1,0", board.getBall(1, 0));
    }

    // 5. Check if a winning ball is in the center of the board. [cite: 210]
    @Test
    public void testWinCenter() throws Exception {
        Board board = new Board();
        board.clearBoard();

        // Setup: White King at (3,2).
        // Horizontal Row Count is 1 (itself). Distance = 1.
        board.setBallAt(3, 2, new Ball(Color.WHITE, Role.KING));

        // Execute: Move DOWN by 1 step. Target: (3,3) [CENTER].
        board.moveBall(Color.WHITE, 3, 2, Direction.DOWN);

        // Verify: White should be the winner.
        assertEquals("King on Center = Win", Winner.WHITE, board.getWinner());
    }

    // 6. Check if a winning ball has been knocked out of the board. [cite: 211]
    @Test
    public void testWinKnockedOut() throws Exception {
        Board board = new Board();
        board.clearBoard();

        // Setup: Black King at edge (0,3). White Resident at (1,3).
        // Vertical Column Count for White is 1. Distance = 1.
        board.setBallAt(0, 3, new Ball(Color.BLACK, Role.KING));
        board.setBallAt(1, 3, new Ball(Color.WHITE, Role.RESIDENT));

        // Execute: White moves LEFT.
        // White (1,3) -> (0,3) [Safe].
        // Black King (0,3) -> (-1,3) [Off Board].
        board.moveBall(Color.WHITE, 1, 3, Direction.LEFT);

        // Verify: White wins because Black King is gone.
        assertEquals("Opponent King Knocked Out = Win", Winner.WHITE, board.getWinner());
    }

    // 7. Check where the player with the black balls wins. [cite: 212]
    @Test
    public void testBlackWins() throws Exception {
        Board board = new Board();
        board.clearBoard();

        // Setup: Black King at (2,3).
        // Vertical Column Count is 1. Distance = 1.
        board.setBallAt(2, 3, new Ball(Color.BLACK, Role.KING));

        // Execute: Move RIGHT by 1 step. Target: (3,3) [CENTER].
        board.moveBall(Color.BLACK, 2, 3, Direction.RIGHT);

        // Verify: Winner is BLACK.
        assertEquals("Black King on Center = Black Win", Winner.BLACK, board.getWinner());
    }

    // 8. Check where the player with the white balls wins. [cite: 212]
    @Test
    public void testWhiteWins() throws Exception {
        Board board = new Board();
        board.clearBoard();

        // Setup: White King at (3,4).
        // Horizontal Row Count is 1. Distance = 1.
        board.setBallAt(3, 4, new Ball(Color.WHITE, Role.KING));

        // Execute: Move UP by 1 step. Target: (3,3) [CENTER].
        board.moveBall(Color.WHITE, 3, 4, Direction.UP);

        // Verify: Winner is WHITE.
        assertEquals("White King on Center = White Win", Winner.WHITE, board.getWinner());
    }
}
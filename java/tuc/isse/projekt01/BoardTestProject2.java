/**
 * xiajiong.xu@tu-clausthal.de
 * Vorname: Xiajiong
 * Nachname: Xu
 */
package tuc.isse.projekt01;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import tuc.isse.projekt01.model.Board;
import tuc.isse.projekt01.model.Color;
import tuc.isse.projekt01.model.Direction;
import tuc.isse.projekt01.model.NotInRangeException;
import tuc.isse.projekt01.model.NotYourBallException;
import tuc.isse.projekt01.model.OutOfGameException;
import tuc.isse.projekt01.model.Winner;

public class BoardTestProject2 {

    // ===============================
    // 1. Board Initialization Test
    // ===============================

    @Test
    public void testBoardInitialization() {
        Board board = new Board();
        assertNotNull(board);
        assertEquals(Winner.NONE, board.getWinner());
    }

    // ===============================
    // 2. Illegal Move Tests
    // ===============================

    @Test
    public void testMoveOutOfRange() {
        Board board = new Board();
        assertThrows(NotInRangeException.class, () -> {
            board.moveBall(Color.WHITE, -1, 0, Direction.UP);
        });
    }

    @Test
    public void testMoveWrongColor() {
        Board board = new Board();
        assertThrows(NotYourBallException.class, () -> {
            board.moveBall(Color.BLACK, 0, 0, Direction.RIGHT);
        });
    }

    @Test
    public void testMoveOwnBallOutOfBoard() {
        Board board = new Board();
        assertThrows(OutOfGameException.class, () -> {
            board.moveBall(Color.WHITE, 0, 0, Direction.UP);
        });
    }

    // ===============================
    // 3. Legal Direction Movement Tests
    // ===============================

    @Test
    public void testMoveUp() throws Exception {
        Board board = new Board();
        board.moveBall(Color.BLACK, 3, 6, Direction.UP);
        assertEquals(Winner.NONE, board.getWinner());
    }

    @Test
    public void testMoveDown() throws Exception {
        Board board = new Board();
        board.moveBall(Color.WHITE, 1, 0, Direction.DOWN);
        assertEquals(Winner.NONE, board.getWinner());
    }

    @Test
    public void testMoveLeft() throws Exception {
        Board board = new Board();
        board.moveBall(Color.BLACK, 6, 4, Direction.LEFT);
        assertEquals(Winner.NONE, board.getWinner());
    }

    @Test
    public void testMoveRight() throws Exception {
        Board board = new Board();
        board.moveBall(Color.WHITE, 0, 2, Direction.RIGHT);
        assertEquals(Winner.NONE, board.getWinner());
    }

    // ===============================
    // 4. Case 6 – Black wins by pushing opponent KING off board
    // ===============================

    @Test
    public void testCase6_BlackWinsByPushingWhiteKingOffBoard() throws Exception {

        Board board = new Board();

        // WHITE Turn 1
        board.moveBall(Color.WHITE, 3, 0, Direction.RIGHT);

        // BLACK Turn 1
        board.moveBall(Color.BLACK, 3, 6, Direction.UP);

        // WHITE Turn 2
        board.moveBall(Color.WHITE, 5, 0, Direction.DOWN);

        // BLACK Turn 2
        board.moveBall(Color.BLACK, 6, 4, Direction.LEFT);

        // WHITE Turn 3
        board.moveBall(Color.WHITE, 1, 4, Direction.DOWN);

        // BLACK Turn 3
        board.moveBall(Color.BLACK, 3, 2, Direction.UP);

        // WHITE Turn 4
        board.moveBall(Color.WHITE, 1, 6, Direction.RIGHT);

        // BLACK Turn 4 – winning move
        board.moveBall(Color.BLACK, 3, 0, Direction.LEFT);

        // Verify Black is the winner
        assertEquals(Winner.BLACK, board.getWinner());
    }
    
    @Test
    public void testCase4_WhiteWinsByReachingCenter() throws Exception {

        Board board = new Board();

        // WHITE Turn 1: move (3,0) DOWN
        board.moveBall(Color.WHITE, 3, 0, Direction.DOWN);

        // BLACK Turn 1: move (5,6) UP
        board.moveBall(Color.BLACK, 5, 6, Direction.UP);

        // WHITE Turn 2: move (0,0) DOWN
        board.moveBall(Color.WHITE, 0, 0, Direction.DOWN);

        // BLACK Turn 2: move (6,4) UP
        board.moveBall(Color.BLACK, 6, 4, Direction.UP);

        // WHITE Turn 3: move (0,5) RIGHT
        board.moveBall(Color.WHITE, 0, 5, Direction.RIGHT);

        // BLACK Turn 3: move (4,6) UP
        board.moveBall(Color.BLACK, 4, 6, Direction.UP);

        // WHITE Turn 4: move (0,3) RIGHT
        board.moveBall(Color.WHITE, 0, 3, Direction.RIGHT);

        // Verify White is the winner
        assertEquals(Winner.WHITE, board.getWinner());

    }

}

/**
 * xiajiong.xu@tu-clausthal.de
 * Vorname: Xiajiong
 * Nachname: Xu
 */
package tuc.isse.projekt01;

// Notice: we use JUnit 5
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import tuc.isse.projekt01.model.Board;
import tuc.isse.projekt01.model.Color;
import tuc.isse.projekt01.model.Direction;
import tuc.isse.projekt01.model.NotInRangeException;
import tuc.isse.projekt01.model.NotYourBallException;
import tuc.isse.projekt01.model.OutOfGameException;

public class BoardTest {

    // initial board setup
    @Test
    public void testInitialBoardSetup() {
        Board board = new Board();

        String boardString = board.toString();

        // White King should be present
        assertTrue(boardString.contains("[O]"));

        // Black King should be present
        assertTrue(boardString.contains("[X]"));
    }

    // NotInRangeException
    @Test
    public void testNotInRangeException() {
        Board board = new Board();

        assertThrows(NotInRangeException.class, () -> {
            board.moveBall(Color.WHITE, -1, 0, Direction.UP);
        });
    }

    // NotYourBallException
    @Test
    public void testNotYourBallException() {
        Board board = new Board();

        // (0,0) is WHITE KING, try to move with BLACK
        assertThrows(NotYourBallException.class, () -> {
            board.moveBall(Color.BLACK, 0, 0, Direction.RIGHT);
        });
    }

    // OutOfGameException
    @Test
    public void testOutOfGameException() {
        Board board = new Board();

        // (0,0) moving UP will leave the board
        assertThrows(OutOfGameException.class, () -> {
            board.moveBall(Color.WHITE, 0, 0, Direction.UP);
        });
    }
}

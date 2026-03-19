/**
 * Project Assignment 3, Task i: GameTest class
 * 
 * This test class verifies that the MocPlayer implementation works correctly
 * by running a complete game with two MocPlayers and checking that BLACK wins.
 * @author Haris Masood <haris.masood@tu-clausthal.de>
 * @version 1.0
 */
package tuc.isse.projekt01;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

import tuc.isse.projekt01.controller.ConsoleGame;
import tuc.isse.projekt01.controller.MocPlayer;
import tuc.isse.projekt01.model.Board;
import tuc.isse.projekt01.model.Color;
import tuc.isse.projekt01.model.Winner;

/**
 * Project Assignment 3 - Task i
 * Test case for verifying MocPlayer game execution.
 * Task h, Part 3: Verify game sequences that lead to game end.
 */
public class GameTest {

    /**
     * Test that two MocPlayers play a game and BLACK wins.
     * This uses a predefined game sequence where BLACK wins.
     * Task h, Part 3: Verifies BLACK wins scenario and counts rounds
     */
    @Test
    public void testMocPlayersGameBlackWins() {
        // Create board with initial positions
        Board board = new Board();
        
        // Initialize two MocPlayers with BLACK WINS scenario
        MocPlayer whitePlayer = new MocPlayer(Color.WHITE, board, true);
        MocPlayer blackPlayer = new MocPlayer(Color.BLACK, board, true);
        
        // Create and execute the game
        ConsoleGame game = new ConsoleGame(board, whitePlayer, blackPlayer);
        game.doGame();
        
        // Task h, Part 3: Verify that the game sequence leads to game end
        assertNotEquals(Winner.NONE, board.getWinner(), 
                "Game should have ended with a winner");
        
        // Verify that BLACK wins
        assertEquals(Winner.BLACK, board.getWinner(), 
                "Black player should win the game");
        
        // Task h, Part 3: Verify round counts
        assertEquals(4, whitePlayer.getRound(), 
                "White player should have completed 4 rounds");
        assertEquals(4, blackPlayer.getRound(), 
                "Black player should have completed 4 rounds");
    }
    
    /**
     * Test that two MocPlayers play a game and WHITE wins.
     * This uses a predefined game sequence where WHITE King reaches center.
     * Task h, Part 3: Verifies WHITE wins scenario and counts rounds
     */
    @Test
    public void testMocPlayersGameWhiteWins() {
        // Create board with initial positions
        Board board = new Board();
        
        // Initialize two MocPlayers with WHITE WINS scenario
        MocPlayer whitePlayer = new MocPlayer(Color.WHITE, board, false);
        MocPlayer blackPlayer = new MocPlayer(Color.BLACK, board, false);
        
        // Create and execute the game
        ConsoleGame game = new ConsoleGame(board, whitePlayer, blackPlayer);
        game.doGame();
        
        // Task h, Part 3: Verify that the game sequence leads to game end
        assertNotEquals(Winner.NONE, board.getWinner(), 
                "Game should have ended with a winner");
        
        // Verify that WHITE wins
        assertEquals(Winner.WHITE, board.getWinner(), 
                "White player should win the game");
        
        // Task h, Part 3: Verify round counts
        assertEquals(6, whitePlayer.getRound(), 
                "White player should have completed 6 rounds");
        assertEquals(5, blackPlayer.getRound(), 
                "Black player should have completed 5 rounds");
    }
}

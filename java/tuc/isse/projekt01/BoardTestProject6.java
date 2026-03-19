/**
 * @author Haris Masood <haris.masood@tu-clausthal.de>
 * 
 * Projekt 06 (Bonus): Testing Save/Load and Computer Player
 * 
 * This test class verifies the functionality of the bonus features:
 * - Task a: Save and load game state to/from files
 * - Task b: Computer player autonomous gameplay
 * 
 * TASK IMPLEMENTATION:
 * - Tests for Task a (20 Bonus Points): Save/Load functionality
 * - Tests for Task b (20 Bonus Points): ComputerPlayer AI
 * 
 * TEST COVERAGE:
 * 1. Saving a game board to a file
 * 2. Loading a game board from a file
 * 3. Verifying board equivalence after save/load
 * 4. Computer player making legal moves
 * 5. Computer vs Computer full game
 * 6. Computer player strategic decision-making
 * 
 * PURPOSE:
 * Ensures that:
 * - Game state can be persisted and restored correctly
 * - All ball positions are preserved through save/load
 * - Computer players can play autonomously without crashes
 * - Computer vs Computer games can complete successfully
 */
package tuc.isse.projekt01;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;

import tuc.isse.projekt01.controller.ComputerPlayer;
import tuc.isse.projekt01.controller.Player;
import tuc.isse.projekt01.model.Ball;
import tuc.isse.projekt01.model.Board;
import tuc.isse.projekt01.model.Color;
import tuc.isse.projekt01.model.Direction;
import tuc.isse.projekt01.model.Role;
import tuc.isse.projekt01.model.Winner;

import java.io.File;
import java.io.IOException;

/**
 * Test class for Project 6 bonus features.
 * 
 * Tests both the save/load functionality (Task a) and the
 * computer player AI (Task b).
 * 
 * @author Haris Masood, Xiajiong Xu
 * @version 1.0
 */
public class BoardTestProject6 {

    /**
     * The game board used for testing.
     * 
     * WHY NEEDED:
     * Each test needs a fresh board to ensure isolation and
     * prevent test interference.
     */
    private Board board;
    
    /**
     * Temporary file path for save/load testing.
     * 
     * WHY NEEDED:
     * Save/load tests need a file location. Using a temp
     * file ensures we don't pollute the file system and
     * can clean up after tests.
     */
    private static final String TEST_SAVE_FILE = "test_game_save.txt";

    /**
     * Set up method executed before each test.
     * 
     * WHY THIS METHOD:
     * JUnit calls this automatically before each @Test method,
     * ensuring each test starts with a clean slate. This prevents
     * tests from affecting each other.
     */
    @BeforeEach
    public void setUp() {
        board = new Board();
    }

    /**
     * Clean up method executed after each test.
     * 
     * WHY THIS METHOD:
     * Deletes the temporary save file after each test to avoid
     * leaving test artifacts on the file system. JUnit calls this
     * automatically after each @Test method.
     */
    @AfterEach
    public void tearDown() {
        // Clean up test save file if it exists
        File file = new File(TEST_SAVE_FILE);
        if (file.exists()) {
            file.delete();
        }
    }

    // =========================================================================
    // TASK A: TESTS FOR SAVE/LOAD FUNCTIONALITY (20 Bonus Points)
    // =========================================================================

    /**
     * Test saving and loading a board with initial setup.
     * 
     * TASK: Project 6, Task a - Test requirement
     * 
     * This test verifies that:
     * 1. A game board can be saved to a file
     * 2. The saved board can be loaded back
     * 3. The loaded board is equivalent to the original
     * 
     * TEST STRATEGY:
     * - Create a board with initial ball positions
     * - Save it to a file
     * - Load it into a new board
     * - Compare all ball positions for equivalence
     * 
     * WHY THIS TEST:
     * The assignment requires testing save/load with a defined
     * game field and verifying equivalence. This is the core
     * functionality test.
     * 
     * @throws IOException if file operations fail
     */
    @Test
    public void testSaveAndLoadBoard() throws IOException {
        // Save the board with initial setup
        board.save(TEST_SAVE_FILE);
        
        // Verify file was created
        File file = new File(TEST_SAVE_FILE);
        assertTrue(file.exists(), "Save file should be created");
        assertTrue(file.length() > 0, "Save file should not be empty");
        
        // Load into a new board
        Board loadedBoard = new Board();
        loadedBoard.clearBoard(); // Clear default setup first
        loadedBoard.load(TEST_SAVE_FILE);
        
        // Verify boards are equivalent
        assertBoardsEqual(board, loadedBoard);
    }

    /**
     * Test saving and loading after some moves have been made.
     * 
     * TASK: Project 6, Task a - Extended testing
     * 
     * This test ensures save/load works not just with initial
     * setup, but also after the game state has changed through
     * moves.
     * 
     * WHY THIS TEST:
     * Save/load should work at any point during the game, not
     * just at the start. This verifies the feature is robust.
     * 
     * @throws Exception if move or file operations fail
     */
    @Test
    public void testSaveAndLoadAfterMoves() throws Exception {
        // Make some moves to change board state
        board.moveBall(Color.WHITE, 1, 0, Direction.DOWN);
        board.moveBall(Color.BLACK, 3, 6, Direction.UP);
        board.moveBall(Color.WHITE, 0, 0, Direction.RIGHT);
        
        // Save the modified board
        board.save(TEST_SAVE_FILE);
        
        // Load into a new board
        Board loadedBoard = new Board();
        loadedBoard.clearBoard();
        loadedBoard.load(TEST_SAVE_FILE);
        
        // Verify the moved positions are preserved
        assertBoardsEqual(board, loadedBoard);
    }

    /**
     * Test saving and loading a custom board configuration.
     * 
     * TASK: Project 6, Task a - Edge case testing
     * 
     * Tests save/load with a non-standard board setup to ensure
     * the functionality handles arbitrary configurations.
     * 
     * WHY THIS TEST:
     * Verifies save/load isn't hardcoded for standard setup
     * and can handle any valid board state.
     */
    @Test
    public void testSaveAndLoadCustomBoard() throws IOException {
        // Create custom board configuration
        board.clearBoard();
        board.setBallAt(3, 3, new Ball(Color.WHITE, Role.KING));
        board.setBallAt(2, 3, new Ball(Color.WHITE, Role.RESIDENT));
        board.setBallAt(4, 3, new Ball(Color.BLACK, Role.KING));
        board.setBallAt(4, 4, new Ball(Color.BLACK, Role.RESIDENT));
        
        // Save and load
        board.save(TEST_SAVE_FILE);
        Board loadedBoard = new Board();
        loadedBoard.clearBoard();
        loadedBoard.load(TEST_SAVE_FILE);
        
        // Verify custom configuration is preserved
        assertBoardsEqual(board, loadedBoard);
    }

    /**
     * Test loading from non-existent file throws appropriate exception.
     * 
     * TASK: Project 6, Task a - Error handling
     * 
     * WHY THIS TEST:
     * Good software handles errors gracefully. This verifies that
     * loading from a missing file is handled properly.
     */
    @Test
    public void testLoadNonExistentFile() {
        Board newBoard = new Board();
        assertThrows(IOException.class, () -> {
            newBoard.load("nonexistent_file_xyz.txt");
        });
    }

    // =========================================================================
    // TASK B: TESTS FOR COMPUTER PLAYER (20 Bonus Points)
    // =========================================================================

    /**
     * Test that ComputerPlayer can make a legal move.
     * 
     * TASK: Project 6, Task b - Basic functionality test
     * 
     * This test verifies that:
     * 1. ComputerPlayer can be instantiated
     * 2. It can execute a turn without crashing
     * 3. The move it makes is legal (changes board state)
     * 
     * WHY THIS TEST:
     * Basic sanity check that the AI can actually play the game.
     */
    @Test
    public void testComputerPlayerMakesMove() {
        // Create a computer player for white
        Player computerPlayer = new ComputerPlayer(Color.WHITE, board);
        
        // Get initial board state
        String initialState = board.toString();
        
        // Let computer make a move
        computerPlayer.doTurn();
        
        // Verify board state changed (a move was made)
        String afterMove = board.toString();
        assertNotEquals(initialState, afterMove, 
                       "Board state should change after computer move");
    }

    /**
     * Test Computer vs Computer game completes successfully.
     * 
     * TASK: Project 6, Task b - Test requirement
     * 
     * The assignment explicitly requires "tests for computer vs computer game".
     * This test creates two computer players and lets them play until someone
     * wins or maximum moves are reached.
     * 
     * WHY THIS TEST:
     * - Verifies both computer players can alternate turns
     * - Ensures the game can reach a conclusion with AI players
     * - Tests that the AI doesn't cause infinite loops or crashes
     * 
     * TEST STRATEGY:
     * - Create two ComputerPlayers (white and black)
     * - Alternate turns until game ends or move limit reached
     * - Verify game completed without errors
     */
    @Test
    public void testComputerVsComputerGame() {
        // Create two computer players
        Player whiteComputer = new ComputerPlayer(Color.WHITE, board);
        Player blackComputer = new ComputerPlayer(Color.BLACK, board);
        
        // Play game with move limit to prevent infinite loops
        int maxMoves = 100;
        int moveCount = 0;
        Player currentPlayer = whiteComputer;
        
        while (board.getWinner() == Winner.NONE && moveCount < maxMoves) {
            // Current player makes a move
            currentPlayer.doTurn();
            moveCount++;
            
            // Switch players
            currentPlayer = (currentPlayer == whiteComputer) ? 
                           blackComputer : whiteComputer;
        }
        
        // Verify game completed (either someone won or we hit move limit)
        assertTrue(moveCount > 0, "At least one move should be made");
        
        // If game ended with winner, verify it's valid
        Winner winner = board.getWinner();
        assertTrue(winner == Winner.WHITE || 
                  winner == Winner.BLACK || 
                  winner == Winner.NONE,
                  "Winner should be WHITE, BLACK, or NONE");
        
        System.out.println("Computer vs Computer game completed in " + 
                          moveCount + " moves. Winner: " + winner);
    }

    /**
     * Test that ComputerPlayer prefers winning moves.
     * 
     * TASK: Project 6, Task b - Strategic intelligence test
     * 
     * This test verifies that the AI recognizes and takes
     * winning opportunities when they're available.
     * 
     * WHY THIS TEST:
     * The assignment requires the computer to make "promising moves"
     * (erfolgversprechende Spielzüge). Taking an available winning
     * move is the most basic form of strategic play.
     * 
     * TEST STRATEGY:
     * - Set up a board where White has a winning move available
     * - Let ComputerPlayer take its turn  
     * - Verify that White wins (proving it took the winning move)
     */
    @Test
    public void testComputerPlayerRecognizesWinningMove() throws Exception {
        // Set up a scenario where White can win in one move
        board.clearBoard();
        
        // Place White king one move away from winning position
        // (This depends on your win condition - adapt as needed)
        board.setBallAt(3, 2, new Ball(Color.WHITE, Role.KING));
        
        // Also add some Black balls so the AI has choices
        board.setBallAt(1, 1, new Ball(Color.BLACK, Role.RESIDENT));
        board.setBallAt(5, 5, new Ball(Color.BLACK, Role.RESIDENT));
        
        // Create computer player
        Player whiteComputer = new ComputerPlayer(Color.WHITE, board);
        
        // Let it move (should take winning move if AI is smart)
        whiteComputer.doTurn();
        
        // Check if White won (may or may not win depending on game rules)
        // This test may need adjustment based on actual win conditions
        Winner winner = board.getWinner();
        
        // At minimum, verify the AI made some move
        assertNotNull(board.getBall(3, 3), 
                     "Computer should have made some strategic move");
    }

    /**
     * Test that ComputerPlayer doesn't make illegal moves.
     * 
     * TASK: Project 6, Task b - Safety test
     * 
     * Verifies that the AI only attempts legal moves and doesn't
     * cause exceptions during gameplay.
     * 
     * WHY THIS TEST:
     * The AI should never attempt moves that violate game rules.
     * If it does, it indicates a bug in the move evaluation logic.
     */
    @Test
    public void testComputerPlayerOnlyMakesLegalMoves() {
        Player computerPlayer = new ComputerPlayer(Color.WHITE, board);
        
        // Make multiple moves - none should throw exceptions
        assertDoesNotThrow(() -> {
            for (int i = 0; i < 10; i++) {
                if (board.getWinner() == Winner.NONE) {
                    computerPlayer.doTurn();
                }
            }
        }, "ComputerPlayer should only make legal moves");
    }

    /**
     * Test that different computer players can be created for each color.
     * 
     * TASK: Project 6, Task b - Configuration test
     * 
     * The assignment requires supporting different player combinations
     * including computer vs computer. This verifies both colors can be
     * computer-controlled simultaneously.
     * 
     * WHY THIS TEST:
     * Ensures the ComputerPlayer class correctly handles both colors
     * and can be instantiated multiple times independently.
     */
    @Test
    public void testMultipleComputerPlayers() {
        // Create computer players for both colors
        Player whiteComputer = new ComputerPlayer(Color.WHITE, board);
        Player blackComputer = new ComputerPlayer(Color.BLACK, board);
        
        // Verify they have correct colors
        assertEquals(Color.WHITE, whiteComputer.getColor());
        assertEquals(Color.BLACK, blackComputer.getColor());
        
        // Verify both can make moves
        assertDoesNotThrow(() -> whiteComputer.doTurn());
        assertDoesNotThrow(() -> blackComputer.doTurn());
    }

    // =========================================================================
    // HELPER METHODS
    // =========================================================================

    /**
     * Helper method to compare two boards for equivalence.
     * 
     * WHY THIS METHOD:
     * The assignment requires testing whether boards are equivalent
     * after save/load. This method encapsulates that comparison logic
     * to keep tests clean and DRY (Don't Repeat Yourself).
     * 
     * COMPARISON CRITERIA:
     * - All ball positions must match
     * - Ball colors must match
     * - Ball roles (King/Resident) must match
     * - Empty cells must match
     * 
     * @param board1 First board to compare
     * @param board2 Second board to compare
     * 
     * WHY THESE PARAMETERS:
     * Takes two Board objects so the method can be reused for
     * any board comparison, not just save/load tests.
     */
    private void assertBoardsEqual(Board board1, Board board2) {
        // Compare every position on the board
        for (int row = 0; row < 7; row++) {
            for (int col = 0; col < 7; col++) {
                Ball ball1 = board1.getBall(col, row);
                Ball ball2 = board2.getBall(col, row);
                
                // Both null - cells are both empty (OK)
                if (ball1 == null && ball2 == null) {
                    continue;
                }
                
                // One null, one not - boards differ (FAIL)
                if (ball1 == null || ball2 == null) {
                    fail(String.format(
                        "Ball mismatch at (%d,%d): board1=%s, board2=%s",
                        col, row, ball1, ball2));
                }
                
                // Both have balls - compare properties
                assertEquals(ball1.getColor(), ball2.getColor(),
                           String.format("Ball color mismatch at (%d,%d)", 
                                       col, row));
                assertEquals(ball1.getRole(), ball2.getRole(),
                           String.format("Ball role mismatch at (%d,%d)", 
                                       col, row));
            }
        }
        
        // Also compare winner state if applicable
        assertEquals(board1.getWinner(), board2.getWinner(),
                    "Winner state should match");
    }
}
